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

LOC_TOKEN_RE = re.compile(r"^[A-Za-zĂÂÎȘȚăâîșț \-]+$")

BAD_LOCATION_EXACT = {
    "nu, mulțumesc",
    "nu, multumesc",
    "accept",
    "acceptă",
    "accepta",
    "respinge",
    "refuz",
    "închide",
    "inchide",
    "setări",
    "setari",
    "preferințe",
    "preferinte",
    "acasă",
    "acasa",
    "adaugă anunț",
    "adauga anunt",
}

BAD_LOCATION_KEYS = {
    "publi24ro",
    "adaugaanunt",
    "adaugaanunturi",
    "contulmeu",
    "autentificare",
    "inregistrare",
    "cautare",
    "acasa",
}

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

        price = clean_text(price_text)

        # --- LOCATION (collect candidates, then pick best) ---
        location_candidates: list[str] = []

        for extractor in (
            self._extract_location_structural,        # de obicei dă "Timis, Timisoara"
            self._extract_location_from_links,        # idem (Timis + Timisoara)
            self._extract_location_from_jsonld,       # uneori doar oraș (fără județ)
            self._extract_location_from_text_block,   # fallback (mai “murdar”)
        ):
            try:
                cand = extractor(soup)
            except Exception:
                cand = None
            cand = clean_text(cand) if cand else None
            if cand:
                location_candidates.append(cand)

        # încă un fallback “near”, dar îl tratăm ca ultim candidat
        meta = soup.select_one("[class*='location'], [class*='Localitate'], [id*='location'], [class*='zona']")
        root_for_location = meta if meta else (h1.parent if h1 else soup)
        near = self._extract_location_near(root_for_location)
        near = clean_text(near) if near else None
        if near:
            location_candidates.append(near)

        location = self._pick_best_location(location_candidates)

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

        # sanitize location (evită header/cookie/cta)
        if location and self._is_bad_location(location):
            location = None

        return Product(
            source="publi24",
            category=category,
            url=url,
            title=title,
            price=price,
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
    def _sanitize_location(loc: Optional[str]) -> Optional[str]:
        if not loc:
            return None
        norm = clean_text(loc).strip()
        if not norm:
            return None
        low = norm.lower()
        if low in BAD_LOCATION_EXACT:
            return None
        return norm

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
            if clean_text(ss).strip().lower() in BAD_LOCATION_EXACT:
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
        # 1) JSON-LD (dacă există)
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
                        try:
                            return datetime.fromisoformat(dp.replace("Z", "+00:00")).astimezone(timezone.utc)
                        except Exception:
                            pass
            except Exception:
                continue

        # 2) Publi24: "Valabil din 3/1/2026 7:45:39 PM"
        full = soup.get_text("\n", strip=True)
        m = re.search(
            r"(?i)\bvalabil\s+din\s+(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)?\b",
            full,
        )
        if m:
            month, day, year, hh, mm, ss, ampm = m.groups()
            try:
                hour = int(hh)
                if ampm:
                    ampm = ampm.upper()
                    if ampm == "PM" and hour != 12:
                        hour += 12
                    if ampm == "AM" and hour == 12:
                        hour = 0

                dt = datetime(
                    int(year), int(month), int(day),
                    hour, int(mm), int(ss),
                    tzinfo=timezone.utc
                )
                return dt
            except ValueError:
                return None

        # 3) fallback vechi: dd.mm.yyyy
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
    
    @staticmethod
    def _extract_location_from_text_block(soup: BeautifulSoup) -> Optional[str]:
        full = soup.get_text("\n", strip=True)
        lines = [ln.strip() for ln in full.splitlines() if ln.strip()]

        for i, ln in enumerate(lines):
            if ln.lower().startswith("valabil din"):
                # căutăm înapoi maxim 3 linii pentru ceva "Jud, Oras"
                for j in range(i - 1, max(-1, i - 4), -1):
                    cand = clean_text(lines[j])
                    if not cand:
                        continue
                    low = cand.lower().strip()

                    if low in BAD_LOCATION_EXACT:
                        continue

                    if "," in cand and any(ch.isalpha() for ch in cand):
                        return cand
                    # acceptă și un singur oraș (fără virgulă), dacă arată ca un loc
                    if "," not in cand:
                        low = cand.lower().strip()
                        if low not in BAD_LOCATION_EXACT and 3 <= len(cand) <= 35 and any(ch.isalpha() for ch in cand):
                            # exclude chestii obvious non-location
                            if not any(x in low for x in ("lei", "ron", "valabil", "laptop", "ssd", "ram")):
                                return cand
                            
        # fallback: caută în primele 60 linii prima apariție "Jud, Oras"
        for ln in lines[:60]:
            cand = clean_text(ln)
            low = cand.lower().strip()
            if not cand or low in BAD_LOCATION_EXACT:
                continue
            if "lei" in low or "ron" in low or "valabil" in low:
                continue
            if 4 <= len(cand) <= 60 and "," in cand and any(ch.isalpha() for ch in cand):
                return cand
        return None
    
    @staticmethod
    def _extract_location_from_links(soup: BeautifulSoup) -> Optional[str]:
        """
        Fallback strict:
        - NU mai ia primele link-uri din pagină (header/nav).
        - Încearcă să ia județ + oraș doar din zona din jurul textului "Valabil din".
        """
        val = soup.find(string=re.compile(r"(?i)\bvalabil\s+din\b"))
        if not val:
            return None

        # urcăm în DOM până găsim un container care are câteva link-uri (județ/oraș)
        parent = val.parent
        for _ in range(6):
            if parent is None:
                break

            links = parent.find_all("a", href=True)
            texts = []
            for a in links:
                txt = clean_text(a.get_text(" ", strip=True))
                if not txt:
                    continue

                # filtrăm mizerii / meniu
                low = txt.strip().lower()
                if low in BAD_LOCATION_EXACT:
                    continue
                if "adauga" in low and "anunt" in low:
                    continue
                if "acasa" in low:
                    continue
                if ("publi" in low and "24" in low and "ro" in low):
                    continue

                # lungimi rezonabile
                if len(txt) < 3 or len(txt) > 40:
                    continue

                texts.append(txt)

            # dacă avem măcar 2, luăm primele 2 (de obicei județ + oraș)
            if len(texts) >= 2:
                cand = f"{texts[0]}, {texts[1]}"
                # ultima siguranță: nu returnăm “Acasă / Adaugă anunț”
                if clean_text(cand).strip().lower() in BAD_LOCATION_EXACT:
                    return None
                return clean_text(cand)

            parent = parent.parent

        return None

    @staticmethod
    def _extract_location_structural(soup: BeautifulSoup) -> Optional[str]:
        # caută un bloc care conține "Valabil din" și colectează vecinii <a>
        # (de obicei județ + oraș sunt link-uri)
        val = soup.find(string=re.compile(r"(?i)\bvalabil\s+din\b"))
        if not val:
            return None

        parent = val.parent
        # urcăm puțin în DOM ca să prindem containerul
        for _ in range(4):
            if parent is None:
                break
            links = parent.find_all("a")
            texts = [clean_text(a.get_text(" ", strip=True)) for a in links]
            texts = [t for t in texts if t and 2 < len(t) < 30]
            # dacă avem 2 bucăți, e aproape sigur județ+oraș
            bad_words = ("publi24", "cont", "login", "contact", "anunt", "anunț")
            texts2 = []
            for t in texts:
                low = t.lower()
                if low in BAD_LOCATION_EXACT:
                    continue
                if any(w in low for w in bad_words):
                    continue
                texts2.append(t)

            if len(texts2) >= 2:
                return clean_text(f"{texts2[0]}, {texts2[1]}")
            parent = parent.parent

        return None
    
    @staticmethod
    def _pick_best_location(candidates: list[str]) -> Optional[str]:
        """
        Alege cel mai bun candidat.
        Preferăm:
        - "Judet, Oras" (are virgulă)
        - să nu fie texte din cookie / UI
        - să nu fie prea lung / zgomotos
        """
        best: Optional[str] = None
        best_score = -1

        for cand in candidates:
            if not cand:
                continue

            low = clean_text(cand).strip().lower()

            # aruncăm gunoiul (cookie / UI)
            if low in BAD_LOCATION_EXACT:
                continue

            # aruncăm chestii exagerat de lungi
            if len(cand) > 60:
                continue

            # scor: preferăm județ+oraș (virgulă)
            score = 0
            if "," in cand:
                score += 100

            # mic bonus dacă sunt litere și nu e doar cifre
            if any(ch.isalpha() for ch in cand):
                score += 5

            # bonus mic pentru “arătare” (mai specific)
            score += min(len(cand), 40)  # max 40

            if score > best_score:
                best_score = score
                best = cand

        if best and "," in best:
            a, b = [x.strip() for x in best.split(",", 1)]
            if a.lower() == b.lower():
                best = b

        return best
    
    @staticmethod
    def _is_bad_location(loc: str) -> bool:
        if not loc:
            return True

        low = clean_text(loc).strip().lower()
        if low in BAD_LOCATION_EXACT:
            return True

        # cheie normalizată: scoate spații, puncte, diacritice “de bază” rămân ok
        key = re.sub(r"[^a-z0-9]+", "", low)
        if key in BAD_LOCATION_KEYS:
            return True

        # cazuri cu spațieri dubioase “publi 24 .ro”
        if "publi" in low and "24" in low and "ro" in low:
            return True
        if "adauga" in low and "anunt" in low:
            return True
        if "acasa" in key:
            return True

        return False