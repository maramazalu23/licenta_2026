from __future__ import annotations

import re
import html
from urllib.parse import urljoin

SPACE_RE = re.compile(r"\s+")
MPN_RE = re.compile(r"\b([A-Z0-9]{2,6}[-_][A-Z0-9]{2,10}(?:[-_][A-Z0-9]{1,10})?)\b")

BRANDS = [
    "asus", "acer", "lenovo", "hp", "dell", "msi", "apple", "huawei",
    "samsung", "xiaomi", "sony", "gigabyte", "razer", "toshiba", "fujitsu"
]
BRAND_REGEXES = [(b, re.compile(rf"\b{re.escape(b)}\b", re.IGNORECASE)) for b in BRANDS]
MACBOOK_RE = re.compile(r"\bmacbook\b", re.IGNORECASE)


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