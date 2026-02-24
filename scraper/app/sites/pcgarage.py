from __future__ import annotations

import json
import re
from typing import Iterable, List, Optional, Dict, Any, Tuple

from bs4 import BeautifulSoup

from app.core.http import HttpClient
from app.core.utils import clean_text, to_absolute_url, guess_brand, guess_mpn
from app.models import Product
from app.sites.base import SiteScraper


class PcGarageScraper(SiteScraper):
    BASE_URL = "https://www.pcgarage.ro"

    CATEGORY_URLS = {
        # conform linkului tău
        "laptopuri": "https://www.pcgarage.ro/notebook-laptop/",
    }

    DETAIL_HREF_RE = re.compile(r"^/notebook-laptop/[^/]+/.+/?$", re.IGNORECASE)

    def __init__(self, http: HttpClient):
        super().__init__(http)

    def iter_listing_urls(self, category: str, max_pages: int) -> Iterable[str]:
        base = self.CATEGORY_URLS.get(category)
        if not base:
            raise ValueError(f"Unknown category '{category}' for PCGarage.")

        yield base

        for p in range(2, max_pages + 1):
            base_slash = base if base.endswith("/") else base + "/"
            yield f"{base_slash}pagina{p}/"

    def parse_listing_page(self, html: str) -> List[str]:
        soup = BeautifulSoup(html, "lxml")
        urls: set[str] = set()

        for a in soup.select(".product_box_name a[href]"):
            href = a.get("href")
            if not href:
                continue

            # normalize
            if href.startswith("http"):
                abs_url = href
            else:
                abs_url = to_absolute_url(self.BASE_URL, href)

            if not abs_url:
                continue

            # filtrează doar produse
            path = abs_url[len(self.BASE_URL):] if abs_url.startswith(self.BASE_URL) else ""
            if path and not self.DETAIL_HREF_RE.search(path):
                continue

            urls.add(abs_url.split("#", 1)[0])

        return sorted(urls)

    def parse_detail_page(self, html: str, url: str, category: str) -> Product:
        soup = BeautifulSoup(html, "lxml")

        title = self._extract_title(soup) or "UNKNOWN"
        price, currency = self._extract_price_and_currency(soup)
        availability = self._extract_availability(soup)
        desc_text, desc_html = self._extract_description(soup)
        specs_raw = self._extract_specs(soup)

        brand = guess_brand(title)

        mpn = None
        if specs_raw:
            mpn = specs_raw.get("Cod producator") or specs_raw.get("Cod producător")
        if not mpn:
            mpn = guess_mpn(title) or guess_mpn(desc_text)

        return Product(
            source="pcgarage",
            category=category,
            url=url,
            title=title,
            price=price,
            currency=currency or "RON",
            availability=availability,
            description_text=desc_text,
            description_html=desc_html,
            brand_guess=brand,
            mpn_guess=mpn,
            specs_raw=specs_raw if specs_raw else None,
        )

    @staticmethod
    def _extract_title(soup: BeautifulSoup) -> Optional[str]:
        h1 = soup.find("h1")
        if h1:
            t = clean_text(h1.get_text(" ", strip=True))
            if t:
                return t

        og = soup.find("meta", attrs={"property": "og:title"})
        if og and og.get("content"):
            t = clean_text(og.get("content"))
            if t:
                return t

        return None

    @staticmethod
    def _iter_jsonld_objects(soup: BeautifulSoup) -> Iterable[Dict[str, Any]]:
        for s in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
            raw = (s.string or s.get_text(strip=True) or "").strip()
            if not raw:
                continue
            try:
                data = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                continue

            if isinstance(data, dict):
                yield data
            elif isinstance(data, list):
                for it in data:
                    if isinstance(it, dict):
                        yield it

    def _extract_price_and_currency(self, soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
        # 1) JSON-LD: suportă @graph + Product/Offer/AggregateOffer + @type list
        def iter_objs(obj):
            if isinstance(obj, dict):
                yield obj
                if "@graph" in obj and isinstance(obj["@graph"], list):
                    for g in obj["@graph"]:
                        yield from iter_objs(g)
            elif isinstance(obj, list):
                for it in obj:
                    yield from iter_objs(it)

        for obj in self._iter_jsonld_objects(soup):
            for o in iter_objs(obj):
                t = o.get("@type") or ""
                if isinstance(t, list):
                    t = " ".join(map(str, t))
                t_low = str(t).lower()

                # Product -> offers
                if "product" in t_low:
                    offers = o.get("offers")
                    price, cur = self._offers_to_price_currency(offers)
                    if price is not None:
                        return price, cur

                # Offer direct
                if "offer" in t_low:
                    price = o.get("price") or o.get("lowPrice") or o.get("highPrice")
                    cur = o.get("priceCurrency")
                    if price is not None:
                        return str(price), (str(cur) if cur else None)

        # 2) meta itemprop=price (+ currency)
        meta_price = soup.find(attrs={"itemprop": "price"})
        if meta_price:
            content = meta_price.get("content") or meta_price.get("value") or meta_price.get_text(" ", strip=True)
            if content:
                cur = None
                meta_cur = soup.find(attrs={"itemprop": "priceCurrency"})
                if meta_cur:
                    cur = meta_cur.get("content") or meta_cur.get("value") or meta_cur.get_text(" ", strip=True)
                return clean_text(content), (clean_text(cur) if cur else "RON")

        # 3) OpenGraph product:price:amount / currency
        og_amount = soup.find("meta", attrs={"property": re.compile(r"product:price:amount", re.I)})
        if og_amount and og_amount.get("content"):
            og_cur = soup.find("meta", attrs={"property": re.compile(r"product:price:currency", re.I)})
            cur = og_cur.get("content") if og_cur else "RON"
            return clean_text(og_amount.get("content")), clean_text(cur) if cur else "RON"

        # 4) Selectori vizibili (mai mulți)
        for sel in [
            ".ps_price .price_num",
            ".ps_price .price",
            ".ps_price",
            ".price_num",
            ".price",
            "[data-price]",
            "[itemprop='price']",
        ]:
            node = soup.select_one(sel)
            if node:
                if node.has_attr("data-price"):
                    return clean_text(str(node.get("data-price"))), "RON"
                txt = clean_text(node.get_text(" ", strip=True))
                if txt:
                    # păstrează doar numere/virgulă/punct/spații
                    m = re.search(r"(\d{1,3}(?:[.\s]\d{3})*(?:[.,]\d{2})?)", txt)
                    if m:
                        return clean_text(m.group(1)), "RON"

        # 5) fallback regex pe tot textul
        text = soup.get_text(" ", strip=True)
        m = re.search(r"(\d{1,3}(?:[\s\.]\d{3})*(?:[\.,]\d{2})?)\s*(lei|ron)\b", text, re.IGNORECASE)
        if m:
            return clean_text(m.group(1)), "RON"

        return None, None

    @staticmethod
    def _extract_availability(soup: BeautifulSoup) -> Optional[str]:
        for obj in PcGarageScraper._iter_jsonld_objects(soup):
            offers = obj.get("offers")
            if isinstance(offers, dict) and offers.get("availability"):
                return clean_text(str(offers.get("availability")).split("/")[-1])

        avail_node = soup.select_one(".ps_availability")
        if avail_node:
            t = clean_text(avail_node.get_text(" ", strip=True))
            if t:
                return t

        return None

    @staticmethod
    def _extract_specs(soup: BeautifulSoup) -> Dict[str, Any]:
        specs: Dict[str, Any] = {}
        selectors = [
            "#software-specifications-table",
            "#specificatii",
            ".product-specs",
            "table",
        ]

        for sel in selectors:
            table = soup.select_one(sel)
            if not table:
                continue

            rows = table.find_all("tr")
            kv_count = 0
            for tr in rows:
                tds = tr.find_all(["td", "th"])
                if len(tds) == 2:
                    k = clean_text(tds[0].get_text(" ", strip=True))
                    v = clean_text(tds[1].get_text(" ", strip=True))
                    if k and v:
                        specs[k] = v
                        kv_count += 1

            if kv_count >= 5:
                return specs

        return specs

    @staticmethod
    def _extract_description(soup: BeautifulSoup) -> Tuple[Optional[str], Optional[str]]:
        desc_node = soup.select_one("#product-description-container") or soup.select_one(".product-description")
        if desc_node:
            return clean_text(desc_node.get_text(" ", strip=True)), str(desc_node)
        return None, None