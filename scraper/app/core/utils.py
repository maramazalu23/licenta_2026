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

# Acceptă și coduri care încep cu cifre (Lenovo: 16ARP10, 15IRX11 etc.)
MODEL_TOKEN_RE = re.compile(r"\b([A-Z0-9]{2,12}(?:-[A-Z0-9]{1,6})?)\b")

# Cazuri cu spațiu: "A16 3VH"
MODEL_SPACE_RE = re.compile(r"\b([A-Z]{1,3}\d{1,3})\s+([A-Z0-9]{2,6})\b")

BAD_PREFIXES = ("RTX", "GTX", "SSD", "RAM", "CORE", "RYZEN", "INTEL", "AMD", "GB", "HZ", "WUXGA", "FHD", "OLED")

# prinde token-uri gen ANV15-41 / P1503CVA / E1504FA / 16ARP10 / 15IRX11
TOKEN_RE = re.compile(r"\b([A-Z0-9]{2,12}(?:-[A-Z0-9]{1,6})?)\b", re.IGNORECASE)

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

def _has_letters_and_digits(s: str) -> bool:
    return any(c.isalpha() for c in s) and any(c.isdigit() for c in s)

def guess_model(title: str) -> Optional[str]:
    t = (title or "").strip()
    if not t:
        return None

    # 1) pattern-urile tale existente (prioritare)
    for rx in MODEL_PATTERNS:
        m = rx.search(t)
        if m:
            parts = [p for p in m.groups() if p]
            out = " ".join(parts).strip()
            return out or None

    low = t.lower()

    # 2) Brand/series keywords (ex: ThinkPad P51, Legion 5, Nitro V 15)
    # încearcă să întoarcă "ThinkPad P51" / "Legion Pro 7" / "Nitro V 15" etc.
    SERIES_PATTERNS = [
        re.compile(r"\b(thinkpad)\s+([a-z]?\d{2,4}[a-z]{0,3})\b", re.IGNORECASE),
        re.compile(r"\b(legion)\s+(pro\s+\d+|slim\s+\d+|\d+)\b", re.IGNORECASE),
        re.compile(r"\b(ideapad)\s+([a-z0-9 ]{1,20}?)\s+([a-z]{0,3}\d{2,4}[a-z0-9]{0,6})\b", re.IGNORECASE),
        re.compile(r"\b(nitro)\s+([a-z]?\s*v\s*\d{1,2})\b", re.IGNORECASE),
        re.compile(r"\b(vivobook)\s+([a-z0-9]{4,10})\b", re.IGNORECASE),
        re.compile(r"\b(expertbook)\s+([a-z0-9]{3,12})\b", re.IGNORECASE),
        re.compile(r"\b(zenbook)\s+([a-z0-9]{3,12})\b", re.IGNORECASE),
        re.compile(r"\b(omen|pavilion|probook|elitebook)\s+([a-z0-9\-]{2,12})\b", re.IGNORECASE),
        re.compile(r"\b(precision|latitude|inspiron|xps)\s+(\d{3,4})\b", re.IGNORECASE),
        re.compile(r"\b(macbook)\s+(air|pro)\b", re.IGNORECASE),
    ]
    for rx in SERIES_PATTERNS:
        m = rx.search(t)
        if m:
            parts = [p for p in m.groups() if p]
            out = " ".join(parts)
            out = re.sub(r"\s+", " ", out).strip()
            return out or None
        
    # 2.1) Lenovo ThinkBook: "ThinkBook 16 G8 IRL"
    m = re.search(r"\bThinkBook\s+(\d{2})\s+G(\d)\s+([A-Z0-9]{2,6})\b", t, re.IGNORECASE)
    if m:
        # păstrăm formatul frumos
        return f"ThinkBook {m.group(1)} G{m.group(2)} {m.group(3).upper()}"

    # 2.2) Lenovo LOQ: "LOQ 15IAX9" / "LOQ Essential 15IRX11"
    m = re.search(r"\bLOQ\s+(Essential\s+)?(\d{2}[A-Z0-9]{3,6})\b", t, re.IGNORECASE)
    if m:
        essential = (m.group(1) or "").strip()
        code = m.group(2).upper()
        if essential:
            return f"LOQ Essential {code}"
        return f"LOQ {code}"

    # 2.3) Lenovo V15: "V15 G4 IRU" / "V15 G4 AMN"
    m = re.search(r"\bV(\d{2})\s+G(\d)\s+([A-Z]{2,4})\b", t, re.IGNORECASE)
    if m:
        return f"V{m.group(1)} G{m.group(2)} {m.group(3).upper()}"

    # 2.4) HP 17-cn3004nq (coduri hp de tip xx-yy1234zz)
    m = re.search(r"\b(\d{2}-[a-z]{2}\d{4}[a-z0-9]{0,3})\b", t, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    
    # 2.5) Gigabyte A16 3VH / A16 CTH
    m = re.search(r"\bA(\d{2})\s+([A-Z0-9]{3})\b", t, re.IGNORECASE)
    if m:
        return f"A{m.group(1)} {m.group(2).upper()}"
    
    # HP/alte branduri: coduri gen 17-cn3004nq (cu cratimă)
    m = re.search(r"\b(\d{2}-[a-z]{2}\d{4}[a-z0-9]{0,3})\b", t, re.IGNORECASE)
    if m:
        return m.group(1).lower()
    
    m = re.search(r"\bV(\d{2})\s+G(\d)\s+([A-Z]{2,4})\b", t, re.IGNORECASE)
    if m:
        return f"V{m.group(1)} G{m.group(2)} {m.group(3).upper()}"

    # 3) Fallback: caută coduri alfanumerice “de model” (F1605ZA, ANV15-52, 3750ZG etc),
    # dar evită CPU/GPU/RAM/SSD.
    CODE_RX = re.compile(r"\b([A-Z]{1,5}\d{2,5}[A-Z]{0,4}(?:[-/][A-Z0-9]{2,6})?)\b")
    BAD_CODE_RX = re.compile(
        r"^(i[3579]-?\d{3,5}[a-z]{0,3}|"
        r"rtx\d{3,5}(ti)?|gtx\d{3,5}(ti)?|mx\d{3,4}|"
        r"ddr\d|"
        r"\d{1,3}gb|\d{1,2}tb|"
        r"\d{2}\.?(\d)?hz|"
        r"fhd|wuxga|qhd|uhd|oled)$",
        re.IGNORECASE,
    )

    candidates: list[str] = []
    for m in CODE_RX.finditer(t):
        code = m.group(1).strip()
        if not code:
            continue
        if BAD_CODE_RX.match(code):
            continue
        # evită să întoarcă ceva absurd de scurt
        if len(code) < 4:
            continue
        candidates.append(code)

    if candidates:
        # alege cel mai “specific” (de obicei cel mai lung cod)
        candidates.sort(key=len, reverse=True)
        return candidates[0]

    # 4) Ultim fallback: modele simple gen "15s", "G7", "T400"
    SIMPLE_RX = re.compile(r"\b([A-Z]\d{3,4}|15s|g7|t\d{3,4})\b", re.IGNORECASE)
    m = SIMPLE_RX.search(t)
    if m:
        return m.group(1)

    return None