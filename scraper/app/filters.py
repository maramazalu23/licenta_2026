import re

# 1) HARD BAN strict - termeni clar non-laptop sau clar accessory-only
HARD_BAN_STRICT = [
    # audio / periferice / retea / electrocasnice IT non-laptop
    "boxe", "soundbar", "subwoofer", "audio", "amplificator",
    "casti", "căști", "headset",
    "mouse",
    "monitor", "tv", "televizor",
    "imprimanta", "printer", "scanner",
    "router", "switch", "stick",

    # genti / huse / accesorii
    "sacosa", "sacoșa", "cosa", "husă", "husa", "geanta", "geantă",

    # piese / subansamble
    "trackpad", "touchpad", "palmrest", "capac",
    "placa de baza", "placa baza", "motherboard",
    "balama", "balamale",

    # desktop / pc
    "desktop", "unitate pc", "calculator", "sistem",
    "tower", "carcasa pc", "carcasă pc",

    # medii / unitati externe
    "cd extern", "dvd extern", "floppy", "fdd",
    "hard extern", "hdd extern", "ssd extern",

    # alte device-uri
    "telefon", "smartphone", "iphone", "ipad", "tableta", "tabletă",
    "power bank", "powerbank", "baterie externa", "baterie externa",

    # componente de conectivitate
    "modul wireless", "placa wlan", "placă wlan", "wifi adapter",
    "adaptor wifi", "adaptor wi fi", "modul wifi", "modul wi fi",
    "placa wifi", "placă wifi",

    # electronica generica
    "circuite integrate",

    # cazuri problematice observate in DB
    "docking station", "statie laptop", "stație laptop",
    "chromebox", "mini pc",
    "surface pro", "mac studio",
    "unitate optica", "unitate optică",
    "interfata diagnoza", "interfață diagnoză", "diagnoza auto", "diagnoză auto",
    "tester auto", "op com",
]

# 2) Soft component words:
# apar și în anunțuri legitime, deci nu reject direct
SOFT_COMPONENT_WORDS = [
    "baterie", "acumulator",
    "ram", "memorie",
    "ssd", "hdd", "hard disk", "nvme",
    "display", "ecran",
    "incarcator", "încărcător", "alimentator",
    "carcasa", "carcasă",
    "tastatura", "tastatură",
    "dvd",
]

# termeni care, dacă apar la începutul titlului, indică aproape sigur piesă/accesoriu
ACCESSORY_PREFIXES = [
    "baterie", "acumulator", "incarcator", "încărcător", "alimentator",
    "display", "ecran", "modul", "placa", "placă",
    "trackpad", "touchpad", "palmrest", "capac",
    "tastatura", "tastatură", "balama", "balamale",
]

BUNDLE_WORDS = [
    "pachet", "kit", "set",
]

BUY_WANTED_BAN = [
    "cumpar", "cumpăr", "caut", "doresc", "vreau sa cumpar", "achizitionez"
]

DEFECT_PHRASES = [
    "nu porneste", "nu pornește",
    "nu functioneaza", "nu funcționează",
    "pentru piese", "de piese", "pt piese",
    "bios parolat", "parola bios", "parolă bios",
    "fara baterie", "fără baterie",
    "fara incarcator", "fără încărcător",
    "placa video defecta", "placa de baza defecta", "placa bază defectă",
    "dezmembrez", "dezmembrari", "dezmembrări",
]

DEFECT_WORDS = [
    "defect", "defecte", "spart", "sparta", "spartă",
    "crapat", "crăpat", "parolat"
]

ALLOW_KEYWORDS = [
    "laptop", "notebook", "ultrabook", "macbook",
    "thinkpad", "ideapad", "vivobook", "zenbook",
    "latitude", "lattitude", "vostro", "precision",
    "probook", "elitebook", "envy", "pavilion",
    "legion", "rog", "tuf", "omen", "nitro", "predator",
    "aspire", "swift", "matebook", "yoga", "alienware",
]

BRANDS = [
    "asus", "lenovo", "hp", "dell", "acer", "apple", "msi",
    "gigabyte", "huawei", "samsung", "lg", "razer", "alienware",
]

RE_INCH = re.compile(r"\b(1[0-7](?:\.[0-9])?)\s*(?:\"|inch)\b")
RE_CPU = re.compile(r"\b(i[3579]-?\d{3,5}[a-z]{0,2}|ryzen\s*[3579]|r[3579]\s*\d{3,4})\b", re.IGNORECASE)
RE_RAM = re.compile(r"\b(4|8|12|16|24|32|64)\s*gb\b", re.IGNORECASE)
RE_STORAGE = re.compile(r"\b(128|256|512|1024|2048)\s*gb\b|\b(1|2)\s*tb\b", re.IGNORECASE)

def is_valid_publi24_laptop(title, desc, url):
    keep, _ = explain_publi24_laptop_filter(title, desc, url)
    return keep

def _contains_any_word(text: str, words: list[str]) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", text) for w in words)

def _title_starts_with_accessory(title: str) -> bool:
    return any(re.match(rf"^\s*{re.escape(w)}\b", title) for w in ACCESSORY_PREFIXES)

def explain_publi24_laptop_filter(title: str | None, desc: str | None, url: str | None = None) -> tuple[bool, str]:
    """
    Filtru scoring + explain pentru Publi24.
    Returnează (keep, reason).
    """
    t = (title or "").lower().strip()
    d = (desc or "").lower().strip()
    text = f"{t} {d}".strip()

    # 0) cautare / cumpar / wanted
    for b in BUY_WANTED_BAN:
        if re.search(rf"\b{re.escape(b)}\b", text):
            return False, f"wanted_ban:{b}"
        
    # 0.5) bundle / mixed listing dubios
    if _contains_any_word(text, BUNDLE_WORDS):
        suspicious_extra = [
            "diagnoza", "diagnoză", "tester auto", "interfata", "interfață",
            "imprimanta", "imprimantă", "monitor", "telefon", "tableta", "tabletă"
        ]
        if any(x in text for x in suspicious_extra):
            return False, "bundle_mixed_listing"

    # 1) defect / piese
    for b in DEFECT_PHRASES:
        if b in text:
            return False, f"defect_ban:{b}"

    for w in DEFECT_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", text):
            return False, f"defect_ban:{w}"
        
    # 1.5) device-uri clar non-laptop
    explicit_non_laptop = [
        "surface pro", "mac studio", "chromebox", "mini pc"
    ]
    if any(x in text for x in explicit_non_laptop):
        return False, "explicit_non_laptop"

    # 2) hard ban clar non-laptop in TITLU
    for b in HARD_BAN_STRICT:
        if re.search(rf"\b{re.escape(b)}\b", t):
            return False, f"title_hard_ban_strict:{b}"

    # 3) reject direct pentru titluri de tip piesa/accesoriu
    # ex: "Baterie laptop Toshiba", "Modul wireless pentru laptop", "Incarcator Dell"
    has_laptop_word = _contains_any_word(text, ["laptop", "notebook", "macbook"])
    has_allow_kw = _contains_any_word(text, ALLOW_KEYWORDS)
    has_brand = _contains_any_word(text, BRANDS)
    has_tech_specs = bool(RE_INCH.search(text) or RE_CPU.search(text) or RE_RAM.search(text) or RE_STORAGE.search(text))

    if _title_starts_with_accessory(t):
        if not (has_allow_kw and has_brand and has_tech_specs):
            return False, "reject_accessory_prefix"

    # 4) daca titlul contine doar componente si nu are semnal suficient de laptop, reject
    has_soft_component_in_title = _contains_any_word(t, SOFT_COMPONENT_WORDS)
    strong_laptop_signal = (
        has_laptop_word
        or has_allow_kw
        or (has_brand and has_tech_specs)
    )

    if has_soft_component_in_title and not strong_laptop_signal:
        return False, "reject_component_only"

    score = 0
    reasons = []

    # 5) scoring pozitiv
    if has_laptop_word:
        score += 4
        reasons.append("laptop_kw(+4)")
    elif has_allow_kw:
        score += 3
        reasons.append("allow_kw(+3)")

    if has_brand:
        score += 2
        reasons.append("brand(+2)")

    if RE_INCH.search(text):
        score += 2
        reasons.append("inch(+2)")

    if RE_CPU.search(text):
        score += 2
        reasons.append("cpu(+2)")

    if RE_RAM.search(text) or RE_STORAGE.search(text):
        score += 1
        reasons.append("ram_or_storage(+1)")

    # 6) penalizare moderata daca descrierea contine termeni suspecti,
    # dar nu reject automat
    desc_bans = [b for b in HARD_BAN_STRICT if re.search(rf"\b{re.escape(b)}\b", d)]
    if desc_bans:
        score -= 1
        reasons.append(f"desc_hard_ban(-1):{','.join(desc_bans[:3])}")

    # 7) prag final
    keep = score >= 4
    reason = (
        f"{'ok' if keep else 'reject'}: score={score}; " + " ".join(reasons)
        if reasons else
        f"{'ok' if keep else 'reject'}: score={score}"
    )
    return keep, reason