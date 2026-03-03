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
    "publi24",
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


def normalize_condition(
    condition: Optional[str],
    *,
    source: Optional[str] = None,
    specs_raw: Optional[dict] = None,
) -> Optional[str]:
    """
    Normalizează condiția în: 'new' / 'used' / None
    Acceptă RO/EN: nou/sigilat/nefolosit, folosit/utilizat/uzat, second-hand/sh etc.
    """

    # 1) ia din specs_raw dacă există (ex: publi24 -> specs_raw["stare"])
    cand = None
    if specs_raw and isinstance(specs_raw, dict):
        stare = specs_raw.get("stare")
        if isinstance(stare, str) and stare.strip():
            cand = stare

    # 2) fallback pe condition text
    if cand is None:
        cand = condition

    if not cand:
        # fallback sigur pe sursă (retail)
        if (source or "").lower() == "pcgarage":
            return "new"
        return None

    s = cand.strip().lower()

    # normalizează separatori / variații
    s = s.replace("-", " ").replace("_", " ")
    s = " ".join(s.split())

    NEW = {
        "nou", "sigilat", "nefolosit", "nou nout", "noua", "nouă", "noua nout",
        "brand new", "new", "sealed",
    }
    USED = {
        "folosit", "utilizat", "uzat", "second hand", "second", "sh", "used",
        "refurbished", "reconditionat", "recondiționat",
    }

    if s in NEW:
        return "new"
    if s in USED:
        return "used"

    # pattern-uri (în caz că apare în propoziție)
    if any(k in s for k in ("sigilat", "nefolosit", "brand new")):
        return "new"
    if any(k in s for k in ("folosit", "second hand", "second-hand", "utilizat", "uzat", "sh")):
        return "used"

    # fallback per sursă
    if (source or "").lower() == "pcgarage":
        return "new"

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


def normalize_title(title: str) -> str:
    t = clean_text(title) or ""
    t = re.sub(r"(?i)\b(sigillat|sigilat!!+|urgent|super oferta|oferta)\b", "", t)
    return clean_text(t) or ""