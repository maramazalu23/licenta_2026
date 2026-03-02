import re

HARD_BAN_STRICT = [
    # accesorii/piese/servicii sau categorii clar non-laptop
    "boxe", "soundbar", "subwoofer", "audio", "amplificator",
    "casti", "căști", "headset",
    "tastatura", "mouse", "încărcător", "incarcator", "alimentator",
    "ventilator",
    "placa de baza", "placa baza", "motherboard",
    "balama", "carcasa", "carcasă",
    "dezmembr", "dezmembrez", "dezmembrari", "piese",
    "service", "repar", "repara", "reparatii", "reparații",
    "monitor", "tv", "televizor",
    "imprimanta", "printer", "scanner",
    "router", "switch", "stick",
    "sacosa", "cosa", "husa"
]

HARD_BAN_SOFT = [
    # apar frecvent în titluri legitime de laptop
    "baterie", "acumulator",
    "ram", "memorie",
    "ssd", "hdd", "hard disk", "nvme",
    "display", "ecran",
]

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
    "router", "switch", "stick", "trackpad",
    "capac", "touchpad", "palmrest",
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

RE_INCH = re.compile(r"\b(1[0-7](?:\.[0-9])?)\s*(?:\"|inch)\b")
RE_CPU = re.compile(r"\b(i[3579]-?\d{3,5}[a-z]{0,2}|ryzen\s*[3579]|r[3579]\s*\d{3,4})\b", re.IGNORECASE)
RE_RAM = re.compile(r"\b(4|8|12|16|24|32|64)\s*gb\b", re.IGNORECASE)
RE_STORAGE = re.compile(r"\b(128|256|512|1024|2048)\s*gb\b|\b(1|2)\s*tb\b", re.IGNORECASE)

def is_valid_publi24_laptop(title, desc, url):
    keep, _ = explain_publi24_laptop_filter(title, desc, url)
    return keep

def explain_publi24_laptop_filter(title: str | None, desc: str | None, url: str | None = None) -> tuple[bool, str]:
    """
    APLICA EXACT aceeași logică ca is_valid_publi24_laptop, dar întoarce și motivul.
    Motivul te ajută să vezi dacă filtrul e prea agresiv.
    """
    t = (title or "").lower()
    d = (desc or "").lower()
    u = (url or "").lower()
    text = f"{t} {d}"

    # 1) hard ban în titlu
    for b in HARD_BAN_STRICT:
        if re.search(rf"\b{re.escape(b)}\b", t):
            return False, f"title_hard_ban_strict:{b}"
    
    score = 0
    reasons = []

    # 3) semnale puternice
    if any(k in text for k in ALLOW_KEYWORDS):
        score += 3
        reasons.append("allow_kw(+3)")

    if any(b in text for b in BRANDS):
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

    # 4) penalizare dacă apar hard-ban în descriere
    desc_bans = [b for b in HARD_BAN_STRICT if re.search(rf"\b{re.escape(b)}\b", d)]
    if desc_bans:
        score -= 1
        # nu listăm toate, doar primele 3 ca să nu umple log-ul
        sample = ",".join(desc_bans[:3])
        reasons.append(f"desc_hard_ban(-1):{sample}")

    keep = score >= 3
    reason = f"{'ok' if keep else 'reject'}: score={score}; " + " ".join(reasons) if reasons else f"{'ok' if keep else 'reject'}: score={score}"
    return keep, reason