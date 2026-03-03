from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple

from app.models import Product
from app.core.utils import clean_text


# tokens pe care NU vrem să le acceptăm ca "location" validă
BAD_LOC_SUBSTR = (
    "adaugă anunț",
    "acasă",
    "publi",
    "cookie",
    "consent",
    "gdpr",
)

LOC_SEP_RE = re.compile(r"\s*,\s*")


def normalize_location(location: Optional[str]) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Returnează (location_clean, county, city)
    - dacă ai "Bucuresti, Sector 3" => county="Bucuresti", city="Sector 3"
    - dacă ai "Iasi" => county=None, city="Iasi"
    """
    if not location:
        return None, None, None

    loc = clean_text(location)
    if not loc:
        return None, None, None

    low = loc.lower()
    if any(b in low for b in BAD_LOC_SUBSTR):
        return None, None, None

    parts = [p.strip() for p in LOC_SEP_RE.split(loc) if p.strip()]
    if len(parts) >= 2:
        return loc, parts[0], parts[1]
    return loc, None, parts[0]


def normalize_condition(p: Product) -> Optional[str]:
    """
    Încercăm să scoatem o condiție standard: new/used/unknown.
    - Publi24: în scraper tu bagi uneori specs_raw["stare"] (ex: "folosit"). :contentReference[oaicite:2]{index=2}
    - PCGarage: de regulă e nou (site retail).
    """
    # dacă ai ceva explicit în specs_raw
    if p.specs_raw and isinstance(p.specs_raw, dict):
        stare = p.specs_raw.get("stare")
        if isinstance(stare, str) and stare.strip():
            s = stare.strip().lower()
            if s in ("nou", "sigilat", "nefolosit"):
                return "new"
            if s in ("folosit", "second", "utilizat", "uzat"):
                return "used"

    # fallback per sursă
    if p.source == "pcgarage":
        return "new"
    if p.source == "publi24":
        return "used"

    return None


def effective_posted_at(p: Product) -> datetime:
    """
    Pentru analytics ai nevoie de o dată.
    - dacă există posted_at -> folosim
    - altfel -> scraped_at (ex: PCGarage nu are posted_at în DB la tine)
    """
    dt = p.posted_at or p.scraped_at
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def price_ron_float(price: Optional[Decimal]) -> Optional[float]:
    if price is None:
        return None
    try:
        return float(price)
    except Exception:
        return None


def normalize_title(title: str) -> str:
    t = clean_text(title)
    # scoate spam clasic
    t = re.sub(r"(?i)\b(sigillat|sigilat!!+|urgent|super oferta|oferta)\b", "", t)
    return clean_text(t)