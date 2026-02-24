from __future__ import annotations

import random
import time
import gzip
from dataclasses import dataclass
from typing import Optional, Dict, Any
from urllib.parse import urlsplit

import requests
from app.config.base import HTTP

import atexit

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

    def polite_sleep(self):
        """Pauză variabilă pentru a imita comportamentul uman."""
        time.sleep(random.uniform(HTTP.min_delay_s, HTTP.max_delay_s))

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> FetchResult:
        last_exc = None
        for attempt in range(1, HTTP.max_retries + 1):
            start = time.time()
            try:
                parts = urlsplit(url)
                base_referer = f"{parts.scheme}://{parts.netloc}/"

                headers = dict(self.session.headers)
                headers["Referer"] = base_referer

                resp = self.session.get(url, params=params, headers=headers, timeout=HTTP.timeout_s)

                if resp.encoding is None or resp.encoding == "ISO-8859-1":
                    resp.encoding = resp.apparent_encoding

                elapsed_ms = int((time.time() - start) * 1000)

                # 1. Verificăm dacă suntem blocați (403) pe PC Garage
                if resp.status_code == 403 and "pcgarage.ro" in url:
                    print(f"[http] 403 la {url} -> retry cu Playwright...")
                    return self.get_js(url, params=params)

                # 2. Extragem textul
                text = resp.text

                if resp.status_code in (429, 503):
                    backoff = HTTP.backoff_base_s * (2 ** (attempt - 1))
                    print(f"Rate limited ({resp.status_code}) la {url}. Retry {attempt} după {backoff}s...")
                    time.sleep(backoff)
                    continue

                # 3. Fallback pentru Publi24 (pagini shell sau compresie defectuoasă)
                if "publi24.ro" in url and resp.status_code == 200:
                    # 1) dacă textul nu pare HTML, încearcă reparare gzip manual
                    if text and "<html" not in text.lower():
                        raw = resp.content
                        if raw[:2] == b"\x1f\x8b":
                            try:
                                text = gzip.decompress(raw).decode(resp.apparent_encoding or "utf-8", errors="replace")
                            except Exception as e:
                                print(f"[http] Eroare decompresie manuală: {e}")

                    # 2) dacă tot nu avem linkuri de anunț, e “shell/JS” -> Playwright
                    if "/anunt/" not in text.lower():
                        print(f"[http] Publi24 suspect HTML (no /anunt/). Retry cu Playwright: {url}")
                        return self.get_js(url, params=params)

                return FetchResult(
                    url=url,
                    status_code=resp.status_code,
                    text=text,
                    elapsed_ms=elapsed_ms,
                )

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
        domain = "pcgarage.ro" if "pcgarage.ro" in url else ("publi24.ro" if "publi24.ro" in url else "default")
        ctx = self._get_context(domain)
        page = ctx.new_page()
        page.route("**/*", lambda route, request: route.abort()
                if request.resource_type in ("image", "media", "font")
                else route.continue_())

        try:
            resp = page.goto(url, wait_until="domcontentloaded", timeout=HTTP.timeout_s * 1000)
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