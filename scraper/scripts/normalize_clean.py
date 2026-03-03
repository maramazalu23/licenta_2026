import re
import sqlite3
import json
from app.config.base import DB_PATH

BRAND_ALIASES = {
    "hp": "HP",
    "hewlett packard": "HP",
    "lenovo": "Lenovo",
    "asus": "ASUS",
    "acer": "Acer",
    "dell": "Dell",
    "msi": "MSI",
    "apple": "Apple",
    "macbook": "Apple",
    "sony": "Sony",
    "vaio": "Sony",
    "samsung": "Samsung",
}

COND_MAP = {
    "nou": "new",
    "sigilat": "new",
    "ca nou": "like_new",
    "ca noua": "like_new",
    "folosit": "used",
    "utilizat": "used",
    "second": "used",
}

CPU_RE = re.compile(
    r"\b("
    r"i[3579]-?\d{4,5}[a-z]{0,2}"
    r"|ryzen(?:™)?\s*[3579]\s*\d{4,5}[a-z]{0,2}"
    r"|core(?:™)?\s*(?:i[3579]|[3579])\s*\d{3,4}[a-z]{0,2}"
    r"|ultra(?:™)?\s*[579]\s*\d{3,4}[a-z]{0,2}"
    r")\b",
    re.I,
)

RAM_RE = re.compile(r"\b(4|8|12|16|24|32|48|64)\s*gb\b(?:\s*(?:ram|ddr[345]|lpddr[45]))?", re.I)

SSD_RE = re.compile(
    r"\b(128|256|512|1024|2048)\s*gb\s*(ssd|nvme)\b"
    r"|\b(1|2)\s*tb\s*(ssd|nvme)\b",
    re.I,
)

GPU_RE = re.compile(
    r"\b("
    r"rtx\s*\d{3,4}\s*(?:ti|super)?"
    r"|gtx\s*\d{3,4}"
    r"|radeon\s*(?:rx\s*)?\d{3,4}m?"
    r"|p\d{3,4}"
    r")\b",
    re.I,
)

SCREEN_RE = re.compile(r"(?:^|[^0-9])((?:1[0-9]|2[0-9])(?:[.,]\d)?)\s*(?:\"|''|inch|inci)", re.I)

MODEL_STOP = {
    "laptop", "notebook", "gaming", "business", "procesor", "processor",
    "intel", "amd", "ryzen", "core", "geforce", "rtx", "gtx",
    "ram", "ssd", "nvme", "hdd", "fhd", "wuxga", "ips", "oled",
    "windows", "win", "no", "os",
}

NON_LAPTOP_KEYWORDS = [
    "baterie", "battery",
    "display", "ecran",
    "unitate optica", "unitate optică", "dvd", "cd r", "cd-r", "rw",
    "incarcator", "încărcător", "alimentator", "adaptor", "adapter",
    "tastatura", "mouse", "trackpad",
    "carcasa", "carcasă", "balama", "hinge",
    "placa de baza", "placă de bază", "motherboard",
    "tower", "desktop", "unitate pc",
]

PCG_MODEL_RE = re.compile(r"/notebook-laptop/[^/]+/(?P<slug>[^/]+)/?$", re.I)

def guess_model_from_pcgarage_url(url: str) -> str | None:
    if not url:
        return None
    m = PCG_MODEL_RE.search(url)
    if not m:
        return None

    slug = m.group("slug")

    patterns = [
        r"\b(anv\d{2}-\d{2})\b",            # ANV15-52
        r"\b(fx\d{3,4}[a-z]{1,3})\b",       # FX707VJ
        r"\b([a-z]\d{4}[a-z]{2,4})\b",      # B1503CVA / P1503CVA / F1605ZA (fallback bun)
        r"\b(\d{2}[a-z]{2,5}\d{1,3}[a-z]?)\b",  # 16iax10h / 15irx11 / 16imh9 (din slug)
        r"\b(\d{2}-[a-z]{2}\d{4}[a-z]{2,3})\b",   # 17-cn3004nq
    ]

    for pat in patterns:
        mm = re.search(pat, slug, re.I)
        if mm:
            cand = mm.group(1).upper()
            if cand.lower() not in MODEL_STOP and len(cand) >= 3:
                return cand

    return None


def norm_title(s: str) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    s = s.replace("™", "").replace("®", "")
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    return s


def guess_model_norm(title: str) -> str | None:
    t = (title or "").replace("™", " ").replace("®", " ")

    # MacBook Retina 12
    m = re.search(r"\bmacbook\s+retina\s+(1[0-6])\b", t, re.I)
    if m:
        return f"MacBook {m.group(1)}"

    # MacBook Air/Pro 13/14/15/16 (nu dublăm "MacBook")
    m = re.search(r"\bmacbook\s+(air|pro)\b.*?\b(1[3-6])\b", t, re.I)
    if m:
        kind = m.group(1).title()
        size = m.group(2)
        return f"MacBook {kind} {size}"
    
    # HP 15s / 15 / 250 G8 etc.
    m = re.search(r"\bhp\s+((?:15s|15)\b(?:[- ]?[a-z]{1,3}\d{2,4})?)", t, re.I)
    if m:
        return m.group(1).upper().replace(" ", "")

    # 0) modele care încep cu cifre (IMPORTANT pt: 16IMH9, 15IRX11, 16IAX10H)
    m = re.search(r"\b(\d{2}[A-Z]{2,5}\d{1,3}[A-Z]?)\b", t, re.I)
    if m:
        return m.group(1).upper()

    low = t.lower()

    # IGNORĂ Quadro P4000 etc. (GPU), nu model laptop
    # (ThinkPad P51 e P + 2 cifre, nu intră aici)
    if ("nvidia" in low or "quadro" in low) and re.search(r"\bp\d{4}\b", t, re.I):
        # nu returnăm P4000 ca model
        pass
    # Dell 7720 / 5530 etc. (4 cifre lângă Dell)
    m = re.search(r"\bdell\s+(\d{4})\b", t, re.I)
    if m:
        return m.group(1)

    # 1) modele "cod" clasice (F1605ZA, ANV15-52, T480, P51 etc.)
    m = re.search(r"\b([A-Z]{1,4}\d{2,5}[A-Z]{0,3}(?:-\d{2})?)\b", t)
    if m:
        cand = m.group(1).strip()
        if cand.lower() not in MODEL_STOP and len(cand) >= 3:
            return cand

    # 2) HP dv4-4141us (și similar)
    m = re.search(r"\b(dv\d-\d{4}[a-z]{0,3})\b", t, re.I)
    if m:
        return m.group(1).upper()

    # 3) “ThinkBook 16 G8 IRL” (îl păstrăm ca model family)
    m = re.search(r"\b(thinkbook\s+\d{2}\s+g\d+\s+[a-z]{2,4})\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip().title()

    # 4) “Legion Pro 7” (fără cod) / “Yoga Pro 9”
    m = re.search(r"\b(legion\s+pro\s+\d+|yoga\s+pro\s+\d+)\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip().title()

    # 5) “Pavilion 14”, “MacBook 12”, “Aspire One” (fallback-uri safe)
    m = re.search(r"\b(pavilion\s+\d{2})\b", t, re.I)
    if m:
        return m.group(1).title()

    m = re.search(r"\b(aspire\s+one)\b", t, re.I)
    if m:
        return "Aspire One"
        # HP 15s / 15 / 250 / 255 etc. (serii scurte)
    m = re.search(r"\b(hp)\s+(15s|14s|15|17)\b", t, re.I)
    if m:
        return f"HP {m.group(2).upper()}"

    # Acer Aspire 3/5/7 + cod dacă există
    m = re.search(r"\b(aspire)\s+(3|5|7)\b", t, re.I)
    if m:
        return f"Aspire {m.group(2)}"

    # Samsung Book 4 / Book 3 etc.
    m = re.search(r"\b(samsung)\s+(book)\s+(\d)\b", t, re.I)
    if m:
        return f"Book {m.group(3)}"

    # Pavilion g7 / g6 etc.
    m = re.search(r"\b(pavilion)\s+(g\d)\b", t, re.I)
    if m:
        return f"Pavilion {m.group(2).upper()}"
    
    # Lenovo Y520 / Y540 etc.
    m = re.search(r"\b([y]\d{3,4})\b", t, re.I)
    if m:
        return m.group(1).upper()

    # HP EliteBook 850 G4 / 840 G5 etc.
    m = re.search(r"\b(elitebook)\s+(\d{3})\s+(g\d)\b", t, re.I)
    if m:
        return f"EliteBook {m.group(2)} {m.group(3).upper()}"

    # Dell "i7 4510U" -> nu e model, dar prindem seria dacă există (ex: Inspiron 15 3000 etc.)
    # Dacă nu există, mai bine lăsăm NULL (ca să nu inventăm model)
    m = re.search(r"\b(inspiron|latitude|precision|vostro|xps)\s+(\d{3,4})\b", t, re.I)
    if m:
        return f"{m.group(1).title()} {m.group(2)}"

    # Zenbook 13 / Zenbook 14 (când nu există UX/UM/număr)
    m = re.search(r"\b(zenbook)\s+(\d{2})\b", t, re.I)
    if m:
        return f"Zenbook {m.group(2)}"

    # HP Chromebook (generic -> îl punem ca familie)
    m = re.search(r"\b(chromebook)\b", t, re.I)
    if m:
        return "Chromebook"

    m = re.search(r"\b(hp)\s+chrome\b", t, re.I)
    if m:
        return "Chromebook"
    
    # Acer Aspire 3750ZG / 5750G etc.
    m = re.search(r"\b(aspire)\s+([0-9]{3,4}[a-z]{0,3})\b", t, re.I)
    if m:
        return f"Aspire {m.group(2).upper()}"
    
    m = re.search(r"\b(zenbook)\b", t, re.I)
    if m:
        return "Zenbook"
    
    m = re.search(r"\b(ideapad)\s+(slim)\s+(\d{1,2})\b", t, re.I)
    if m:
        return f"IdeaPad Slim {m.group(3)}"

    return None


def norm_brand(s: str | None) -> str | None:
    if not s:
        return None
    x = s.strip().lower()
    if x in BRAND_ALIASES:
        return BRAND_ALIASES[x]
    for k, v in BRAND_ALIASES.items():
        if k in x:
            return v
    return s.strip()


def norm_condition(title: str, desc: str, specs: dict | None) -> str | None:
    text = f"{title} {desc}".lower()
    if specs and isinstance(specs, dict):
        st = (specs.get("stare") or "").strip().lower()
        if st in COND_MAP:
            return COND_MAP[st]
    for k, v in sorted(COND_MAP.items(), key=lambda kv: len(kv[0]), reverse=True):
        if k in text:
            return v
    return None


def extract(text: str, regex: re.Pattern) -> str | None:
    m = regex.search(text or "")
    return m.group(0).strip() if m else None


def _is_laptop(source: str, title: str, desc: str) -> int:
    if (source or "").lower() == "pcgarage":
        return 1
    low = f"{title} {desc}".lower()
    if any(k in low for k in NON_LAPTOP_KEYWORDS):
        return 0
    return 1


def guess_model_family(brand_norm: str | None, title_norm: str) -> str | None:
    """
    Întoarce o familie 'safe' (nu inventează coduri).
    Doar termeni destul de stabili: Aspire, Zenbook, ThinkPad, EliteBook etc.
    """
    t = (title_norm or "").lower()
    b = (brand_norm or "").lower()

    # Lenovo
    if "thinkpad" in t:
        return "ThinkPad"
    if "thinkbook" in t:
        return "ThinkBook"
    if "ideapad" in t:
        return "IdeaPad"
    if "legion" in t:
        # păstrăm "Legion" / "Legion Pro"
        if "legion pro" in t:
            return "Legion Pro"
        return "Legion"
    if "yoga" in t:
        if "yoga pro" in t:
            return "Yoga Pro"
        return "Yoga"
    if "loq" in t:
        return "LOQ"

    # ASUS
    if "zenbook" in t:
        return "Zenbook"
    if "vivobook" in t:
        return "Vivobook"
    if "tuf" in t:
        return "TUF"
    if "rog" in t or "republic of gamers" in t:
        return "ROG"

    # Acer
    if "aspire one" in t:
        return "Aspire One"
    if "aspire" in t:
        return "Aspire"
    if "nitro" in t:
        return "Nitro"
    if "predator" in t:
        return "Predator"

    # HP
    if "elitebook" in t:
        return "EliteBook"
    if "probook" in t:
        return "ProBook"
    if "pavilion" in t:
        return "Pavilion"
    if "spectre" in t:
        return "Spectre"
    if "envy" in t:
        return "Envy"
    if "chromebook" in t or "chrome" in t:
        return "Chromebook"
    if "business" in t and b == "hp":
        return "Business"

    # Dell
    if "latitude" in t:
        return "Latitude"
    if "inspiron" in t:
        return "Inspiron"
    if "xps" in t:
        return "XPS"
    if "precision" in t:
        return "Precision"
    if "vostro" in t:
        return "Vostro"

    # Apple
    if "macbook air" in t:
        return "MacBook Air"
    if "macbook pro" in t:
        return "MacBook Pro"
    if "macbook" in t:
        return "MacBook"

    # MSI (de obicei au serii, dar păstrăm safe)
    if b == "msi":
        if "katana" in t:
            return "Katana"
        if "stealth" in t:
            return "Stealth"
        if "raider" in t:
            return "Raider"
        if "prestige" in t:
            return "Prestige"

    # Erazer (Medion)
    if "erazer" in t:
        return "Erazer"

    return None


def build_title_std(
    brand_norm: str | None,
    model_family: str | None,
    model_norm: str | None,
    cpu: str | None,
    ram_gb: int | None,
    storage: str | None,
    gpu: str | None,
    screen_in: float | None,
) -> str | None:
    parts: list[str] = []

    b = (brand_norm or "").strip()
    fam = (model_family or "").strip()
    mn = (model_norm or "").strip()

    # dacă model_norm începe deja cu brand (ex: "HP 15S"), nu mai adăugăm brand separat
    if b:
        if not (mn.lower().startswith(b.lower() + " ") or fam.lower().startswith(b.lower() + " ")):
            parts.append(b)

    # dacă family este deja inclusă în model_norm (ex: model_norm="MacBook Air 13"), nu mai punem family
    if fam:
        if not (mn and fam.lower() in mn.lower()):
            parts.append(fam)

    if mn:
        parts.append(mn)

    # specs (scurte)
    if cpu:
        parts.append(cpu)
    if ram_gb:
        parts.append(f"{ram_gb}GB RAM")
    if storage:
        parts.append(storage.upper().replace("  ", " "))
    if gpu:
        parts.append(gpu.upper())
    if screen_in:
        # 15.6 -> "15.6"
        parts.append(f'{screen_in:g}"')

    if not parts:
        return None

    # dedup simplu (păstrează ordinea)
    seen = set()
    out = []
    for p in parts:
        key = p.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(p.strip())

    return " ".join(out).strip() if out else None


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # add columns (safe)
    cols = {r["name"] for r in cur.execute("PRAGMA table_info(products_clean)").fetchall()}

    def addcol(name, ddl):
        if name not in cols:
            cur.execute(f"ALTER TABLE products_clean ADD COLUMN {name} {ddl}")

    addcol("brand_norm", "TEXT")
    addcol("condition_norm", "TEXT")
    addcol("model_norm", "TEXT")
    addcol("title_norm", "TEXT")
    addcol("model_family", "TEXT")
    addcol("title_std", "TEXT")
    addcol("cpu_guess", "TEXT")
    addcol("ram_gb", "INTEGER")
    addcol("storage_guess", "TEXT")
    addcol("gpu_guess", "TEXT")
    addcol("screen_in", "REAL")
    addcol("is_laptop", "INTEGER")

    conn.commit()

    cols = [r["name"] for r in cur.execute("PRAGMA table_info(products_clean)").fetchall()]

    def pick(*names):
        for n in names:
            if n in cols:
                return n
        return None

    col_source = pick("source")
    col_url = pick("url")
    col_title = pick("title", "title_clean", "name", "name_clean")
    col_desc = pick("description_text", "description", "description_clean", "desc", "desc_clean")
    col_brand = pick("brand_guess", "brand", "brand_clean")
    col_specs = pick("specs_raw", "specs", "specs_clean")

    needed = [c for c in [col_source, col_url, col_title, col_desc, col_brand, col_specs] if c is not None]
    rows = cur.execute("SELECT rowid, " + ", ".join(needed) + " FROM products_clean").fetchall()

    updated = 0
    for r in rows:
        source = (r[col_source] if col_source else "") or ""
        url = (r[col_url] if col_url else "") or ""
        title = (r[col_title] if col_title else "") or ""
        desc = (r[col_desc] if col_desc else "") or ""
        raw_brand = (r[col_brand] if col_brand else None)

        specs = None
        if col_specs and r[col_specs]:
            try:
                specs = json.loads(r[col_specs]) if isinstance(r[col_specs], str) else r[col_specs]
            except Exception:
                specs = None

        t_norm = norm_title(title)
        is_laptop = _is_laptop(source, title, desc)

        b = norm_brand(raw_brand or "")
        if not b:
            low = f"{title} {desc}".lower()
            for k, v in BRAND_ALIASES.items():
                if k in low:
                    b = v
                    break

        # model_norm (DOAR dacă e laptop)
        m_norm = None
        if is_laptop == 1:
            if source.lower() == "pcgarage":
                m_norm = guess_model_from_pcgarage_url(url) or guess_model_norm(t_norm)
            else:
                m_norm = guess_model_norm(t_norm)

        # Publi24 = marketplace second-hand -> default used if we can't infer from text/specs
        cond = norm_condition(title, desc, specs)
        if source.lower() == "pcgarage":
            cond = "new"
        if not cond and source.lower() == "publi24":
            cond = "used"

        text = f"{title} {desc}"
        cpu = extract(text, CPU_RE)

        ram = None
        mram = RAM_RE.search(text)
        if mram:
            ram = int(mram.group(1))

        storage = extract(text, SSD_RE)
        gpu = extract(text, GPU_RE)

        scr = None
        ms = SCREEN_RE.search(text)
        if ms:
            try:
                scr = float(ms.group(1).replace(",", "."))
            except Exception:
                scr = None

        # model_family + title_std (DOAR pt laptopuri)
        fam = None
        t_std = None
        if is_laptop == 1:
            fam = guess_model_family(b, t_norm)
            t_std = build_title_std(b, fam, m_norm, cpu, ram, storage, gpu, scr)
        
        cur.execute(
            """
            UPDATE products_clean
            SET brand_norm=?,
                condition_norm=COALESCE(?, condition_norm),
                model_norm=?, title_norm=?,
                model_family=?, title_std=?,
                cpu_guess=?, ram_gb=?, storage_guess=?, gpu_guess=?, screen_in=?,
                is_laptop=?
            WHERE rowid=?
            """,
            (b, cond, m_norm, t_norm,
            fam, t_std,
            cpu, ram, storage, gpu, scr,
            is_laptop, r["rowid"]),
        )
        updated += 1

    conn.commit()
    conn.close()
    print("normalized_updated:", updated)


if __name__ == "__main__":
    main()