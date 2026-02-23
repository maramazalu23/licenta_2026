from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Optional, Dict, Any

import requests
from app.config.base import HTTP


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
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ro-RO,ro;q=0.9,en-US;q=0.8,en;q=0.7",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Cache-Control": "max-age=0",
        })

    def polite_sleep(self):
        """Pauză variabilă pentru a imita comportamentul uman."""
        time.sleep(random.uniform(HTTP.min_delay_s, HTTP.max_delay_s))

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> FetchResult:
        last_exc = None
        for attempt in range(1, HTTP.max_retries + 1):
            start = time.time()
            try:
                # Simulăm Referer-ul ca fiind site-ul principal dacă e prima cerere
                if "Referer" not in self.session.headers:
                    self.session.headers["Referer"] = "https://www.google.com/"

                resp = self.session.get(url, params=params, timeout=HTTP.timeout_s)
                
                # Forțăm encoding-ul corect pentru diacriticele noastre
                if resp.encoding is None or resp.encoding == 'ISO-8859-1':
                    resp.encoding = resp.apparent_encoding

                elapsed_ms = int((time.time() - start) * 1000)

                if resp.status_code in (429, 503):
                    backoff = HTTP.backoff_base_s * (2 ** (attempt - 1))
                    print(f"Rate limited ({resp.status_code}) la {url}. Retry {attempt} după {backoff}s...")
                    time.sleep(backoff)
                    continue

                # Actualizăm Referer pentru următoarea cerere (navigare succesivă)
                self.session.headers["Referer"] = url

                return FetchResult(
                    url=url,
                    status_code=resp.status_code,
                    text=resp.text,
                    elapsed_ms=elapsed_ms,
                )

            except requests.RequestException as e:
                last_exc = e
                backoff = HTTP.backoff_base_s * (2 ** (attempt - 1))
                print(f"Eroare rețea la {url}: {e}. Retry în {backoff}s...")
                time.sleep(backoff)

        raise RuntimeError(f"GET failed after {HTTP.max_retries} retries for {url}: {last_exc}")