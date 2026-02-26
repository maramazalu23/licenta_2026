from __future__ import annotations

import random
import time
import requests
import atexit
import re
import gzip
import logging

from app.config.sites import POLICIES
from collections import defaultdict
from app.config.base import HTTP
from dataclasses import dataclass
from typing import Optional, Dict, Any
from urllib.parse import urlsplit

logger = logging.getLogger("scraper.http")

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
        self._closed = False

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
        if "cloudflare" in low or "challenge" in low or ("cf-" in low and "captcha" in low):
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
                timeout_s = policy.get("timeout_s", HTTP.timeout_s)

                # dacă domeniul e deja în JS mode în run-ul curent, nu mai încerca requests
                if domain in self.js_mode_domains and policy.get("strategy") != "REQUESTS_ONLY":
                    return self.get_js(url, params=params, timeout_s=timeout_s)

                base_referer = f"{parts.scheme}://{parts.netloc}/"
                headers = dict(self.session.headers)
                headers["Referer"] = base_referer

                resp = self.session.get(url, params=params, headers=headers, timeout=timeout_s)

                # rate-limit handling (reintrodus)
                if resp.status_code in (429, 503):
                    self.failure_counter[domain] += 1
                    backoff = HTTP.backoff_base_s * (2 ** (attempt - 1))
                    logger.warning("Rate limited (%s) la %s. Retry %s după %ss...", resp.status_code, url, attempt, backoff)
                    time.sleep(backoff)
                    continue

                # PCGarage: 403 -> JS imediat
                if resp.status_code == 403 and domain == "pcgarage.ro":
                    self.failure_counter[domain] += 1
                    self.js_mode_domains.add(domain)
                    logger.warning("[http] 403 la %s -> JS mode pentru %s (Playwright)", url, domain)
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
                            logger.warning("[http] Switch JS mode pentru %s (failures=%s): %s", domain, self.failure_counter[domain], url)
                            return self.get_js(url, params=params)

                # dacă requests a mers bine, resetăm failures
                self.failure_counter[domain] = 0

                elapsed_ms = int((time.time() - start) * 1000)
                return FetchResult(url=url, status_code=resp.status_code, text=text, elapsed_ms=elapsed_ms)
            
            except requests.RequestException as e:
                last_exc = e
                backoff = HTTP.backoff_base_s * (2 ** (attempt - 1))
                logger.warning("Eroare rețea la %s: %s. Retry în %ss...", url, e, backoff)
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

    def get_js(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        timeout_s: int | float | None = None,
    ) -> FetchResult:
        # params (query string) - le atașăm manual dacă există
        if params:
            from urllib.parse import urlencode
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}{urlencode(params, doseq=True)}"

        last_exc: Exception | None = None

        for attempt in range(1, HTTP.max_retries + 1):
            start = time.time()

            parts = urlsplit(url)
            domain = parts.netloc.lower()
            if domain.startswith("www."):
                domain = domain[4:]

            policy = self._get_policy(domain)

            max_retries = int(policy.get("max_retries", HTTP.max_retries))
            backoff_base = float(policy.get("backoff_base_s", HTTP.backoff_base_s))
            timeout_policy = policy.get("timeout_s", HTTP.timeout_s)

            # timeout: param explicit > policy > HTTP default
            effective_timeout = timeout_policy if timeout_s is None else timeout_s

            page = None
            try:
                ctx = self._get_context(domain)
                page = ctx.new_page()

                # blocăm resurse grele (mai rapid + mai puține șanse de anti-bot)
                page.route(
                    "**/*",
                    lambda route, request: route.abort()
                    if request.resource_type in ("image", "media", "font")
                    else route.continue_(),
                )

                resp = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=int(float(effective_timeout) * 1000),
                )

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

            except Exception as e:
                last_exc = e

                # IMPORTANT: folosim max_retries din policy dacă există
                backoff = backoff_base * (2 ** (attempt - 1))
                logger.warning(
                    "[js] Eroare Playwright la %s (%s/%s): %s: %s. Retry în %.1fs",
                    url,
                    attempt,
                    max_retries,
                    type(e).__name__,
                    e,
                    backoff,
                )
                time.sleep(backoff)

                # dacă policy-ul cere mai puține retry-uri decât HTTP.max_retries, ieșim devreme
                if attempt >= max_retries:
                    break

            finally:
                if page is not None:
                    try:
                        page.close()
                    except Exception:
                        pass

        assert last_exc is not None
        raise last_exc

    def close(self):
        if getattr(self, "_closed", False):
            return
        self._closed = True
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