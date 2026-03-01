import re

HARD_BAN = [
    # non-laptop / accesorii / piese
    "boxe", "soundbar", "subwoofer", "audio", "amplificator",
    "casti", "căști", "headset",
    "tastatura", "mouse", "încărcător", "incarcator", "alimentator",
    "baterie", "acumulator", "ventilator",
    "ram", "memorie", "ssd", "hdd", "hard disk", "nvme",
    "placa de baza", "placa baza", "motherboard",
    "display", "ecran", "balama", "carcasa", "carcasă",
    "dezmembr", "dezmembrez", "dezmembrari", "piese",
    "service", "repar", "repara", "reparatii", "reparații",
    "monitor", "tv", "televizor", "cosa", "sacosa", 
    "imprimanta", "printer", "scanner",
    "router", "switch", "stick", 
]

ALLOW_KEYWORDS = [
    "laptop", "notebook", "ultrabook", "macbook",
    "thinkpad", "ideapad", "vivobook", "zenbook",
    "latitude", "vostro", "precision",
    "probook", "elitebook",
    "legion", "rog", "tuf", "omen", "nitro", "predator",
]

BRANDS = [
    "asus", "lenovo", "hp", "dell", "acer", "apple", "msi",
    "gigabyte", "huawei", "samsung", "lg", "razer",
]

RE_INCH = re.compile(r"\b(1[0-9](?:\.[0-9])?|2[0-9](?:\.[0-9])?)\s*(?:\"|inch)\b")
RE_CPU = re.compile(r"\b(i[3579]-?\d{3,5}[a-z]{0,2}|ryzen\s*[3579]|r[3579]\s*\d{3,4})\b", re.IGNORECASE)
RE_RAM = re.compile(r"\b(4|8|12|16|24|32|64)\s*gb\b", re.IGNORECASE)
RE_STORAGE = re.compile(r"\b(128|256|512|1024|2048)\s*gb\b|\b(1|2)\s*tb\b", re.IGNORECASE)

def is_valid_publi24_laptop(title: str | None, desc: str | None, url: str | None) -> bool:
    t = (title or "").lower()
    d = (desc or "").lower()
    u = (url or "").lower()
    text = f"{t} {d}"

    # 1) hard ban: dacă apare în titlu e aproape sigur non-laptop
    if any(b in t for b in HARD_BAN):
        return False

    # 2) dacă URL indică altă categorie dubioasă, poți exclude (opțional)
    # exemplu: dacă ai observat pattern-uri în URL
    # if "/audio/" in u: return False

    score = 0

    # 3) semnale puternice
    if any(k in text for k in ALLOW_KEYWORDS):
        score += 3

    if any(b in text for b in BRANDS):
        score += 2

    if RE_INCH.search(text):
        score += 2

    if RE_CPU.search(text):
        score += 2

    if RE_RAM.search(text) or RE_STORAGE.search(text):
        score += 1

    # 4) penalizări dacă apar hard-ban în descriere (mai “soft”)
    if any(b in d for b in HARD_BAN):
        score -= 2

    # prag
    return score >= 3

def explain_publi24_laptop_filter(title: str, desc: str, url: str = "") -> tuple[bool, str]:
    """
    Returnează (keep, reason) pentru debugging/audit.
    reason e un string scurt: "ok", "hard_ban:<word>", "missing_inch", etc.
    """
    t = (title or "").lower()
    d = (desc or "").lower()
    text = f"{t}\n{d}"

    # exemplu (adaptează exact la logica ta actuală):
    # 1) hard ban
    for b in HARD_BAN:
        if b in text:
            return False, f"hard_ban:{b}"

    # 2) must have laptop keywords / inch / cpu etc (depinde ce ai)
    # dacă ai deja reguli RE_INCH / RE_CPU etc, le aplici aici și dai reason
    # fallback:
    return True, "ok"