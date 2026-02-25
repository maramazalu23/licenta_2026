from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any
from urllib.parse import urlsplit

import requests
from app.config.base import HTTP

import atexit

import os
import re
import gzip
from collections import defaultdict

try:
    from playwright.sync_api import sync_playwright
except Exception:
    sync_playwright = None


@dataclass
class FetchResult:
    url: str
    status_code: int
    text: str
    elapsed_ms: int

POLICIES = {
    "pcgarage.ro": {
        "strategy": "JS_REQUIRED",     # dacă 403 -> JS imediat
        "timeout_s": 30,
        "min_len": 30_000,
        "must_contain": "/notebook-laptop/",
        "fail_threshold": 1,
    },
    "publi24.ro": {
        "strategy": "JS_IF_SHELL",     # încearcă requests, apoi JS dacă pare shell/challenge
        "timeout_s": 20,
        "min_len": 15_000,
        "must_contain": "/anunt/",
        "fail_threshold": 2,
    },
    "default": {
        "strategy": "REQUESTS_ONLY",
        "timeout_s": 15,
        "min_len": 10_000,
        "must_contain": None,
        "fail_threshold": 3,
    },
}

BLOCKED_TITLE_PATTERNS = [
    r"just a moment",
    r"attention required",
    r"access denied",
    r"forbidden",
    r"are you a human",
    r"captcha",
    r"please enable cookies",
]
BLOCKED_TITLE_RE = re.compile("|".join(BLOCKED_TITLE_PATTERNS), re.IGNORECASE)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


class HttpClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": HTTP.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "DNT": "1",

            # headers tipice de navigare browser
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Sec-Fetch-User": "?1",

            # CH-UA (nu e perfect, dar ajută des)
            "sec-ch-ua": '"Not A(Brand";v="99", "Google Chrome";v="121", "Chromium";v="121"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
        })

        

        self._pw = None
        self._browser = None
        self._context_by_domain = {}
        atexit.register(self.close)
        self.js_mode_domains = set()              # domenii promovate la JS în acest run
        self.failure_counter = defaultdict(int)   # eșecuri consecutive pe requests

    def polite_sleep(self):
        """Pauză variabilă pentru a imita comportamentul uman."""
        time.sleep(random.uniform(HTTP.min_delay_s, HTTP.max_delay_s))

    def _get_policy(self, domain: str) -> Dict[str, Any]:
        # map netloc la domeniul de policy (ex: www.pcgarage.ro -> pcgarage.ro)
        if domain.startswith("www."):
            domain = domain[4:]
        return POLICIES.get(domain, POLICIES["default"])

    def _extract_title(self, html: str) -> str:
        m = TITLE_RE.search(html or "")
        if not m:
            return ""
        return re.sub(r"\s+", " ", m.group(1)).strip().lower()

    def _looks_blocked(self, html: str) -> bool:
        title = self._extract_title(html)
        if title and BLOCKED_TITLE_RE.search(title):
            return True
        low = (html or "").lower()
        # indicatori generali de challenge
        if "cloudflare" in low or "challenge" in low or "cf-" in low and "captcha" in low:
            return True
        return False

    def _looks_shell_or_bad(self, policy: Dict[str, Any], html: str) -> bool:
        if not html:
            return True
        low = html.lower()

        # dacă pare blocat după title/keywords
        if self._looks_blocked(html):
            return True

        must = policy.get("must_contain")
        if must and must.lower() not in low:
            return True

        min_len = policy.get("min_len")
        if min_len and len(html) < int(min_len):
            # semnal slab, dar util ca backup
            return True

        return False

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> FetchResult:
        last_exc = None
        for attempt in range(1, HTTP.max_retries + 1):
            start = time.time()
            try:
                parts = urlsplit(url)
                domain = parts.netloc.lower()
                if domain.startswith("www."):
                    domain = domain[4:]

                policy = self._get_policy(domain)

                # dacă domeniul e deja în JS mode în run-ul curent, nu mai încerca requests
                if domain in self.js_mode_domains and policy.get("strategy") != "REQUESTS_ONLY":
                    return self.get_js(url, params=params)

                base_referer = f"{parts.scheme}://{parts.netloc}/"
                headers = dict(self.session.headers)
                headers["Referer"] = base_referer

                timeout_s = policy.get("timeout_s", HTTP.timeout_s)

                resp = self.session.get(url, params=params, headers=headers, timeout=timeout_s)

                # rate-limit handling (reintrodus)
                if resp.status_code in (429, 503):
                    self.failure_counter[domain] += 1
                    backoff = HTTP.backoff_base_s * (2 ** (attempt - 1))
                    print(f"Rate limited ({resp.status_code}) la {url}. Retry {attempt} după {backoff}s...")
                    time.sleep(backoff)
                    continue

                # PCGarage: 403 -> JS imediat
                if resp.status_code == 403 and domain == "pcgarage.ro":
                    self.failure_counter[domain] += 1
                    self.js_mode_domains.add(domain)
                    print(f"[http] 403 la {url} -> JS mode pentru {domain} (Playwright)")
                    return self.get_js(url, params=params)

                # text normal
                if resp.encoding is None or resp.encoding == "ISO-8859-1":
                    resp.encoding = resp.apparent_encoding

                text = resp.text

                # fallback gzip manual doar dacă nu pare HTML (rar)
                if resp.status_code == 200 and text and "<html" not in text.lower():
                    raw = resp.content
                    if raw[:2] == b"\x1f\x8b":
                        try:
                            text = gzip.decompress(raw).decode(resp.apparent_encoding or "utf-8", errors="replace")
                        except Exception:
                            pass

                # Publi24 / general: detect shell/blocked -> comută la JS după threshold
                if resp.status_code == 200 and policy.get("strategy") == "JS_IF_SHELL":
                    if self._looks_shell_or_bad(policy, text):
                        self.failure_counter[domain] += 1
                        if self.failure_counter[domain] >= int(policy.get("fail_threshold", 2)):
                            self.js_mode_domains.add(domain)
                            print(f"[http] Switch JS mode pentru {domain} (failures={self.failure_counter[domain]}): {url}")
                            return self.get_js(url, params=params)

                # dacă requests a mers bine, resetăm failures
                self.failure_counter[domain] = 0

                elapsed_ms = int((time.time() - start) * 1000)
                return FetchResult(url=url, status_code=resp.status_code, text=text, elapsed_ms=elapsed_ms)
            
            except requests.RequestException as e:
                last_exc = e
                backoff = HTTP.backoff_base_s * (2 ** (attempt - 1))
                print(f"Eroare rețea la {url}: {e}. Retry în {backoff}s...")
                time.sleep(backoff)

        raise RuntimeError(f"GET failed after {HTTP.max_retries} retries for {url}: {last_exc}")
    
    def _ensure_playwright(self):
        if sync_playwright is None:
            raise RuntimeError("Playwright nu este instalat. Rulează: pip install playwright")

        if self._pw is None:
            self._pw = sync_playwright().start()

        if self._browser is None:
            self._browser = self._pw.chromium.launch(headless=True)

    def _get_context(self, domain: str):
        self._ensure_playwright()
        ctx = self._context_by_domain.get(domain)
        if ctx is None:
            ctx = self._browser.new_context(
                user_agent=self.session.headers.get("User-Agent"),
                locale="ro-RO",
                extra_http_headers={
                    "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            self._context_by_domain[domain] = ctx
        return ctx

    def get_js(self, url: str, params: Optional[Dict[str, Any]] = None) -> FetchResult:
        # params (query string) - le atașăm manual dacă există
        if params:
            from urllib.parse import urlencode
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode(params)}"

        start = time.time()
        parts = urlsplit(url)
        domain = parts.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        ctx = self._get_context(domain)
        page = ctx.new_page()
        page.route("**/*", lambda route, request: route.abort()
                if request.resource_type in ("image", "media", "font")
                else route.continue_())

        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=HTTP.timeout_s * 1000, )
            # uneori challenge-ul cere puțin timp
            page.wait_for_timeout(1200)

            html = page.content()
            status = resp.status if resp else 0
            elapsed_ms = int((time.time() - start) * 1000)

            return FetchResult(
                url=url,
                status_code=status,
                text=html,
                elapsed_ms=elapsed_ms,
            )
        finally:
            page.close()

    def close(self):
        # cleanup la ieșirea din program
        try:
            for ctx in self._context_by_domain.values():
                try:
                    ctx.close()
                except Exception:
                    pass
            self._context_by_domain.clear()

            if self._browser is not None:
                try:
                    self._browser.close()
                except Exception:
                    pass
                self._browser = None

            if self._pw is not None:
                try:
                    self._pw.stop()
                except Exception:
                    pass
                self._pw = None
        except Exception:
            pass