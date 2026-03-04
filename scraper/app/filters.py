import re

# 1) HARD BAN strict (clar non-laptop)
HARD_BAN_STRICT = [
    # accesorii/piese/servicii sau categorii clar non-laptop
    "boxe", "soundbar", "subwoofer", "audio", "amplificator",
    "casti", "căști", "headset",
    "tastatura", "mouse", "încărcător", "incarcator", "alimentator",
    "ventilator",
    "placa de baza", "placa baza", "motherboard",
    "balama", "balamale", "carcasa", "carcasă",
    "dezmembr", "dezmembrez", "dezmembrari", "dezmembrări", "piese",
    "service", "repar", "repara", "reparatii", "reparații",
    "monitor", "tv", "televizor",
    "imprimanta", "printer", "scanner",
    "router", "switch", "stick",
    "sacosa", "sacoșa", "cosa", "husă", "husa", "geanta", "geantă",
    "trackpad", "touchpad", "palmrest", "capac",
    "desktop", "pc", "unitate", "unitate pc", "calculator", "sistem",
    "tower", "carcasa pc", "carcasă pc",
    "cd", "dvd", "cd extern", "dvd extern", "floppy", "fdd",
    "hard extern", "hdd extern", "ssd extern",
    "imprimanta", "printer", "scanner",
    "monitor", "tv", "televizor",
]

# 2) Soft bans: cuvinte care apar și în anunțuri legitime (nu reject direct)
SOFT_COMPONENT_WORDS = [
    "baterie", "acumulator",
    "ram", "memorie",
    "ssd", "hdd", "hard disk", "nvme",
    "display", "ecran",
]

BUY_WANTED_BAN = ["cumpar", "cumpăr", "caut", "doresc", "vreau sa cumpar", "achizitionez"]

DEFECT_PHRASES = [
  "nu porneste", "nu pornește", "nu functioneaza", "nu funcționează",
  "pentru piese", "de piese", "pt piese",
  "bios parolat", "parola bios", "parolă bios",
  "fara baterie", "fără baterie", "fara incarcator", "fără încărcător",
  "placa video defecta", "placa de baza defecta", "placa bază defectă",
]

DEFECT_WORDS = ["defect", "defecte", "spart", "sparta", "spartă", "crapat", "crăpat", "parolat"]

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
    Filtru scoring + explain pentru Publi24.
    Returnează (keep, reason).
    """
    t = (title or "").lower()
    d = (desc or "").lower()
    text = f"{t} {d}"

    for b in BUY_WANTED_BAN:
        if re.search(rf"\b{re.escape(b)}\b", text):
            return False, f"wanted_ban:{b}"

    # 0) reject direct dacă sunt semnale clare de defect / pentru piese
    for b in DEFECT_PHRASES:
        if b in text:
            return False, f"defect_ban:{b}"

    for w in DEFECT_WORDS:
        if re.search(rf"\b{re.escape(w)}\b", text):
            return False, f"defect_ban:{w}"

    # 1) hard ban strict în titlu (clar non-laptop)
    for b in HARD_BAN_STRICT:
        if re.search(rf"\b{re.escape(b)}\b", t):
            return False, f"title_hard_ban_strict:{b}"

    # 2) anti-"doar componentă": dacă titlul e despre o piesă și nu există semnale puternice de laptop, reject
    has_soft_component_in_title = any(re.search(rf"\b{re.escape(w)}\b", t) for w in SOFT_COMPONENT_WORDS)
    has_strong_laptop_signal = any(k in text for k in ("laptop", "notebook", "macbook"))
    if has_soft_component_in_title and not has_strong_laptop_signal and not any(b in text for b in BRANDS):
        return False, "reject_component_only"

    score = 0
    reasons = []

    # 3) semnale puternice
    # laptop/notebook/macbook sunt foarte puternice
    if any(k in text for k in ("laptop", "notebook", "macbook")):
        score += 4
        reasons.append("laptop_kw(+4)")
    elif any(k in text for k in ALLOW_KEYWORDS):
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

    # 4) penalizare dacă apar hard-ban în descriere (dar nu reject direct)
    desc_bans = [b for b in HARD_BAN_STRICT if re.search(rf"\b{re.escape(b)}\b", d)]
    if desc_bans:
        score -= 1
        sample = ",".join(desc_bans[:3])
        reasons.append(f"desc_hard_ban(-1):{sample}")

    keep = score >= 3
    reason = (f"{'ok' if keep else 'reject'}: score={score}; " + " ".join(reasons)) if reasons else f"{'ok' if keep else 'reject'}: score={score}"
    return keep, reason