from __future__ import annotations

import re
import html
from urllib.parse import urljoin
from typing import Optional

SPACE_RE = re.compile(r"\s+")
MPN_RE = re.compile(r"\b([A-Z0-9]{2,6}[-_][A-Z0-9]{2,10}(?:[-_][A-Z0-9]{1,10})?)\b")

BRANDS = [
    "asus", "acer", "lenovo", "hp", "dell", "msi", "apple", "huawei",
    "samsung", "xiaomi", "sony", "gigabyte", "razer", "toshiba", "fujitsu"
]
BRAND_REGEXES = [(b, re.compile(rf"\b{re.escape(b)}\b", re.IGNORECASE)) for b in BRANDS]
MACBOOK_RE = re.compile(r"\bmacbook\b", re.IGNORECASE)

MODEL_PATTERNS = [
    # ThinkPad T480, X1 Carbon, etc.
    re.compile(r"\b(thinkpad)\s+([a-z]?\d{3,4}[a-z]?)\b", re.I),
    # Dell Latitude 5420 / Precision 5560
    re.compile(r"\b(latitude|precision|vostro|inspiron)\s+(\d{4})\b", re.I),
    # HP ProBook 450 G8 / EliteBook 840 G7 / Victus 15
    re.compile(r"\b(probook|elitebook)\s+(\d{3,4})\s*(g\d)\b", re.I),
    re.compile(r"\b(victus)\s+(\d{2})\b", re.I),
    # ASUS ROG Strix G16 / TUF F15 / Vivobook 15
    re.compile(r"\b(rog|tuf|vivobook|zenbook)\s+([a-z]?\d{2,4}[a-z]?)\b", re.I),
    # MacBook Pro 14 / Air 13
    re.compile(r"\b(macbook)\s+(air|pro)\s+(\d{2})\b", re.I),
]

def clean_text(s: str | None) -> str | None:
    if s is None:
        return None
    s = html.unescape(s)
    s = s.replace("\xa0", " ")
    s = SPACE_RE.sub(" ", s).strip()
    return s or None


def to_absolute_url(base_url: str, href: str | None) -> str | None:
    if not href:
        return None
    return urljoin(base_url, href)


def guess_mpn(text: str | None) -> str | None:
    if not text:
        return None
    text = clean_text(text) or ""
    m = MPN_RE.search(text.upper())
    return m.group(1) if m else None


def guess_brand(title: str | None) -> str | None:
    if not title:
        return None

    # Prioritate: macbook => Apple
    if MACBOOK_RE.search(title):
        return "APPLE"

    for b, rx in BRAND_REGEXES:
        if rx.search(title):
            return "HP" if b.lower() == "hp" else b.upper()

    return None


def guess_model(title: str) -> Optional[str]:
    t = (title or "").strip()
    if not t:
        return None
    for rx in MODEL_PATTERNS:
        m = rx.search(t)
        if m:
            parts = [p for p in m.groups() if p]
            return " ".join(parts).strip()
    return None