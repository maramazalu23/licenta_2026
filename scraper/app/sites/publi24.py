from __future__ import annotations

import json
import re

from typing import Iterable, List, Optional, Tuple
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from app.core.http import HttpClient
from app.core.utils import clean_text, to_absolute_url, guess_brand, guess_mpn, guess_model
from app.models import Product
from app.sites.base import SiteScraper
from app.filters import explain_publi24_laptop_filter

DATE_RE = re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b")

class Publi24Scraper(SiteScraper):
    """
    Publi24:
    - listare: https://www.publi24.ro/anunturi/electronice/laptop/
    - paginare: ?pag=2, ?pag=3, ...
    - detaliu: .../anunt/<slug>/<id>.html
    """

    BASE_URL = "https://www.publi24.ro"

    CATEGORY_URLS = {
        # MVP: lucrăm pe laptopuri
        "laptopuri": "https://www.publi24.ro/anunturi/electronice/laptop/",
        # Dacă vrei mai târziu:
        # "electronice": "https://www.publi24.ro/anunturi/electronice/",
    }

    DETAIL_HREF_RE = re.compile(r"/anunt/.+\.html", re.IGNORECASE)

    def __init__(self, http: HttpClient):
        super().__init__(http)

    def iter_listing_urls(self, category: str, max_pages: int) -> Iterable[str]:
        base = self.CATEGORY_URLS.get(category)
        if not base:
            raise ValueError(f"Unknown category '{category}' for Publi24. Available: {list(self.CATEGORY_URLS)}")

        # Pagina 1 (fără parametru)
        yield base

        # Pagina 2..N (cu ?pag=)
        # Publi24 folosește ?pag=2 etc.
        for p in range(2, max_pages + 1):
            yield f"{base}?pag={p}"

    def parse_listing_page(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, "lxml")

        urls: set[str] = set()

        for a in soup.select("a[href]"):
            href = a.get("href")
            if not href:
                continue

            # href poate fi relativ
            # cautăm doar link-urile de tip anunț (detail)
            if self.DETAIL_HREF_RE.search(href):
                abs_url = to_absolute_url(self.BASE_URL, href)
                if abs_url:
                    abs_url = abs_url.split("#", 1)[0].split("?", 1)[0]
                    urls.add(abs_url)

        return sorted(urls)

    def parse_detail_page(self, html: str, url: str, category: str) -> Product:
        soup = BeautifulSoup(html, "lxml")

        # Title
        h1 = soup.find("h1")
        title = clean_text(h1.get_text(" ", strip=True)) if h1 else None
        if not title:
            # fallback: <title>
            t = soup.find("title")
            title = clean_text(t.get_text(" ", strip=True)) if t else "UNKNOWN"

        price_text = self._extract_price_from_jsonld(soup)
        if not price_text:
            price_text = self._extract_price_fallback_text(soup)

        price_value = clean_text(price_text)

        # încearcă să găsești o zonă "meta" mai apropiată (best effort)
        location = self._extract_location_from_jsonld(soup)
        if not location:
            meta = soup.select_one("[class*='location'], [class*='Localitate'], [id*='location'], [class*='zona']")
            root_for_location = meta if meta else (h1.parent if h1 else soup)
            location = self._extract_location_near(root_for_location)

        desc_text, desc_html = self._extract_description(soup)

        # specs (în MVP punem doar "stare" dacă o găsim)
        specs_raw = {}
        state = self._extract_state(soup)
        if state:
            specs_raw["stare"] = state

        brand = guess_brand(title)
        mpn = guess_mpn(title or "") or guess_mpn(desc_text or "")

        posted_at = self._extract_posted_at(soup)

        model_guess = guess_model(title)

        return Product(
            source="publi24",
            category=category,
            url=url,
            title=title,
            price=price_value,
            currency="RON",
            availability=None,
            location=location,
            posted_at=posted_at,
            description_text=desc_text,
            description_html=desc_html,
            brand_guess=brand,
            model_guess=model_guess,
            mpn_guess=mpn,
            specs_raw=specs_raw or None,
        )
    
    def filter_product(self, product: "Product") -> bool:
        # Filtrare doar pentru laptopuri (cum ai avut în pipeline)
        if product.category != "laptopuri":
            return True

        title = product.title or ""
        desc = product.description_text or ""
        keep, reason = explain_publi24_laptop_filter(title, desc, product.url)
        if not keep:
            logger = __import__("logging").getLogger("scraper.filter")
            logger.debug("[filtered] %s | %s | %s", reason, product.url, title[:120])
        return keep

    # -------------------
    # Helpers
    # -------------------
    @staticmethod
    def _extract_first_text_with(root, needle: str) -> Optional[str]:
        needle_low = needle.lower()
        for s in root.stripped_strings:
            if needle_low in s.lower():
                return s
        return None

    @staticmethod
    def _extract_location_near(root) -> Optional[str]:
        for s in root.stripped_strings:
            ss = s.strip()
            low = ss.lower()

            # filtre
            if "ron" in low:
                continue
            if len(ss) > 60 or len(ss) < 4:
                continue
            if any(k in low for k in ("laptop", "intel", "ryzen", "ssd", "ram", "rtx", "gtx", "gb", "inch", "\"")):
                continue

            # condiția de locație
            if "," in ss and any(ch.isalpha() for ch in ss):
                return clean_text(ss)

        return None

    @staticmethod
    def _extract_description(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
        """
        Căutăm un header care conține "Descriere" și luăm conținutul de după el.
        În fallback, încercăm să extragem segmentul dintre "Descriere" și "ID anunț:" din textul paginii.
        """
        # 1) încercare structurală (header + fraze după)
        header = soup.find(lambda tag: tag.name in ("h2", "h3", "h4", "h5") and "descriere" in tag.get_text(strip=True).lower())
        if header:
            # adunăm frazele după header până la următorul header mare / secțiune
            parts = []
            html_parts = []
            for sib in header.next_siblings:
                if getattr(sib, "name", None) in ("h2", "h3", "h4", "h5"):
                    break
                # uneori sunt newline-uri (NavigableString)
                text = getattr(sib, "get_text", None)
                if callable(text):
                    t = clean_text(sib.get_text(" ", strip=True))
                    if t:
                        parts.append(t)
                    html_parts.append(str(sib))
            desc_text = clean_text(" ".join(parts)) if parts else None
            desc_html = clean_text(" ".join(html_parts)) if html_parts else None
            return desc_text, desc_html

        # 2) fallback: pe text “flattened”
        full = soup.get_text("\n", strip=True)
        low = full.lower()
        i = low.find("descriere")
        if i == -1:
            return None, None

        # tăiem de la "Descriere" până la "ID anunț" dacă există
        j = low.find("id anun", i)
        segment = full[i:j] if j != -1 else full[i:i + 8000]
        # eliminăm cuvântul "Descriere" din start
        segment = re.sub(r"(?i)^descriere", "", segment).strip()
        return clean_text(segment), None

    @staticmethod
    def _extract_state(soup: BeautifulSoup) -> Optional[str]:
        """
        În exemplu avem "Specificații" -> "Stare" -> "folosit".
        Heuristic: dacă găsim textul "Stare", luăm următorul string.
        """
        strings = list(soup.stripped_strings)
        for idx, s in enumerate(strings):
            if s.strip().lower() == "stare":
                if idx + 1 < len(strings):
                    return clean_text(strings[idx + 1])
        return None
    
    @staticmethod
    def _extract_price_from_jsonld(soup: BeautifulSoup) -> Optional[str]:
        scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
        for sc in scripts:
            try:
                raw = sc.string or sc.get_text(strip=True)
                if not raw: continue
                data = json.loads(raw)
                
                items = data if isinstance(data, list) else [data]
                for it in items:
                    if not isinstance(it, dict): continue
                    
                    # Structură standard Schema.org pentru produse
                    offers = it.get("offers")
                    if isinstance(offers, dict):
                        price = offers.get("price") or offers.get("lowPrice")
                        if price: return str(price)
                    elif isinstance(offers, list) and len(offers) > 0:
                        price = offers[0].get("price")
                        if price: return str(price)
            except Exception:
                continue
        return None

    @staticmethod
    def _extract_price_fallback_text(soup: BeautifulSoup) -> Optional[str]:
        # Regex îmbunătățit pentru a prinde prețuri de tip 1.200, 1200, 1.200,00
        PRICE_RE = re.compile(r"(\d[\d\.\s]*)(?:,(\d{2}))?\s*(lei|ron)\b", re.IGNORECASE)
        candidates = []
        text = soup.get_text(" ", strip=True)

        for m in PRICE_RE.finditer(text):
            num_part = (m.group(1) or "").replace(" ", "").replace(".", "")
            dec_part = m.group(2)
            
            try:
                val_str = f"{num_part}.{dec_part}" if dec_part else num_part
                val = float(val_str)
                if val > 10: # Ignorăm valori nerealiste (gen 1 leu sau erori de regex)
                    candidates.append((val, m.group(0)))
            except:
                continue

        if not candidates: return None
        # Sortăm descrescător după valoarea numerică (prețul e de obicei cea mai mare cifră cu lei/ron)
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]
    
    @staticmethod
    def _extract_posted_at(soup: BeautifulSoup) -> Optional[datetime]:
        # 1) încearcă JSON-LD: datePosted
        scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
        for sc in scripts:
            try:
                raw = sc.string or sc.get_text(strip=True)
                if not raw:
                    continue
                data = json.loads(raw)
                items = data if isinstance(data, list) else [data]
                for it in items:
                    if not isinstance(it, dict):
                        continue
                    dp = it.get("datePosted") or it.get("datePublished")
                    if isinstance(dp, str) and dp:
                        # acceptă ISO (2026-03-01...) sau alte forme; facem best-effort
                        try:
                            # dacă e ISO complet:
                            return datetime.fromisoformat(dp.replace("Z", "+00:00")).astimezone(timezone.utc)
                        except Exception:
                            pass
            except Exception:
                continue

        # 2) fallback: regex dd.mm.yyyy (ce aveai tu)
        text = soup.get_text(" ", strip=True)
        m = DATE_RE.search(text)
        if m:
            dd, mm, yyyy = map(int, m.groups())
            try:
                return datetime(yyyy, mm, dd, tzinfo=timezone.utc)
            except ValueError:
                return None
        return None
    
    @staticmethod
    def _extract_location_from_jsonld(soup: BeautifulSoup) -> Optional[str]:
        scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
        for sc in scripts:
            try:
                raw = sc.string or sc.get_text(strip=True)
                if not raw:
                    continue
                data = json.loads(raw)
                items = data if isinstance(data, list) else [data]
                for it in items:
                    if not isinstance(it, dict):
                        continue

                    # uneori e in "address"
                    addr = it.get("address")
                    if isinstance(addr, dict):
                        city = addr.get("addressLocality") or addr.get("addressCity")
                        region = addr.get("addressRegion")
                        parts = [p for p in [city, region] if isinstance(p, str) and p.strip()]
                        if parts:
                            return clean_text(", ".join(parts))

                    # alteori e in "location"
                    loc = it.get("location")
                    if isinstance(loc, dict):
                        addr = loc.get("address")
                        if isinstance(addr, dict):
                            city = addr.get("addressLocality") or addr.get("addressCity")
                            region = addr.get("addressRegion")
                            parts = [p for p in [city, region] if isinstance(p, str) and p.strip()]
                            if parts:
                                return clean_text(", ".join(parts))
            except Exception:
                continue
        return None