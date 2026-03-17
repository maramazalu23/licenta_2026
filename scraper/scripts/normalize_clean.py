import re
import sqlite3
import json
from app.config.base import DB_PATH
from app.cleaning.normalize import normalize_title, normalize_condition

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
    r"|[Ii][3579]-?\d{3,5}[a-z]{0,2}"
    r"|intel\s+(?:core\s+)?i[3579](?:-\d{3,5}[a-z]{0,2})?"
    r"|ryzen(?:™)?\s*[3579]\s*\d{4,5}[a-z]{0,2}"
    r"|core(?:™)?\s*(?:i[3579]|[3579])\s*\d{3,4}[a-z]{0,2}"
    r"|ultra(?:™)?\s*[579]\s*\d{3,4}[a-z]{0,2}"
    r"|celeron(?:\s+[a-z0-9]+)?"
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
    "docking station", "statie laptop", "stație laptop",
    "chromebox", "mini pc", "desktop", "tower", "unitate pc",
    "unitate optica", "unitate optică",
    "baterie laptop", "battery laptop",
    "incarcator laptop", "încărcător laptop", "alimentator laptop",
    "placa de baza", "placă de bază", "motherboard",
    "trackpad", "touchpad",
    "balama", "hinge",
    "dezmembrez", "pentru piese", "pt piese",
]

PCG_MODEL_RE = re.compile(r"/notebook-laptop/[^/]+/(?P<slug>[^/]+)/?$", re.I)

def plausible_model_guess(s: str | None) -> str | None:
    if not s:
        return None
    x = s.strip()
    low = x.lower()
    banned = {"perfect", "functional", "office", "business", "gaming"}
    if low in banned:
        return None
    if len(x) < 4:
        return None
    if not re.search(r"[0-9]", x) and len(x.split()) == 1:
        return None
    return x

def preprocess_model_text(s: str) -> str:
    s = (s or "").strip().lower()
    fixes = {
        "ellite book": "elitebook",
        "elite book": "elitebook",
        "pro book": "probook",
        "think pad": "thinkpad",
        "mac book": "macbook",
        "fx 505": "fx505",
        "fx 506": "fx506",
        "fx 507": "fx507",
        "fx 508": "fx508",
    }
    for bad, good in fixes.items():
        s = s.replace(bad, good)
    s = re.sub(r"\s+", " ", s).strip()
    return s

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


def guess_model_norm(text: str) -> str | None:
    t = preprocess_model_text(text).replace("™", " ").replace("®", " ")

    # ---------- Apple ----------
    m = re.search(r"\bmacbook\s+retina\s+(1[0-6])\b", t, re.I)
    if m:
        return f"MacBook {m.group(1)}"

    m = re.search(r"\bmacbook\s+(air|pro)\b(?:.*?\b(1[3-6])\b)?", t, re.I)
    if m:
        kind = m.group(1).title()
        size = m.group(2)
        return f"MacBook {kind} {size}" if size else f"MacBook {kind}"

    # ---------- Lenovo / coduri care încep cu cifre ----------
    m = re.search(r"\b(\d{2}[a-z]{2,5}\d{1,3}[a-z]?)\b", t, re.I)   # 16imh9, 15irx11, 16iax10h
    if m:
        return m.group(1).upper()

    m = re.search(r"\b(thinkpad\s+[a-z]?\d{3,4})\b", t, re.I)       # ThinkPad T550, X280
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(thinkbook\s+\d{2}\s+g\d+\s+[a-z]{2,4})\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(ideapad\s+\d{3,4}\s*[a-z0-9-]*)\b", t, re.I)  # Ideapad 700 15ISK / 100 15IBD
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(110-17acl)\b", t, re.I)
    if m:
        return m.group(1).upper()

    m = re.search(r"\b(legion\s+pro\s+\d+)\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(yoga\s+pro\s+\d+)\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b([y]\d{3,4})\b", t, re.I)                      # Y520, Y540
    if m:
        return m.group(1).upper()
    m = re.search(r"\b(legion\s+\d+(?:\s+[a-z0-9]{4,6})?)\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    # ---------- HP ----------
    m = re.search(r"\b(elitebook\s+\d{3}\s*g\d)\b", t, re.I)         # EliteBook 840 G5
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(probook\s+x360\s+\d{3}\s*g\d)\b", t, re.I)    # ProBook x360 435 G8
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(probook\s+\d{3}\s*g\d)\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(pavilion\s+dv\d)\b", t, re.I)                 # Pavilion DV6
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(hp\s+15s[a-z0-9-]*)\b", t, re.I)
    if m:
        return m.group(1).upper().replace(" ", "")

    m = re.search(r"\b(hp\s+(?:15|17|14|550|g7))\b", t, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b(elitebook\s+folio\s+\d{3}\s*g\d)\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(pavilion\s+\d{2}-[a-z0-9-]+)\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(14s-[a-z0-9-]+)\b", t, re.I)
    if m:
        return m.group(1).upper()
    
    m = re.search(r"\b(elitebook\s+\d{3,4}[a-z]?[-\s]g\d)\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1).replace("-", " ")).title()

    # ---------- Dell ----------
    m = re.search(r"\b(xps\s+\d{1,2}\s+\d{4})\b", t, re.I)           # XPS 15 9560
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(xps\s+\d{1,2})\b", t, re.I)                   # XPS 15 / XPS 17
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(inspiron\s+\d{4})\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(latitude\s+\d{4})\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(vostro\s+\d{4,6})\b", t, re.I)                # Vostro 153530
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\bdell\s+(\d{4})\b", t, re.I)                    # Dell 3558 / E5520 separat mai jos
    if m:
        return m.group(1)

    m = re.search(r"\b(e\d{4})\b", t, re.I)                          # E5520
    if m:
        return m.group(1).upper()

    # ---------- ASUS ----------
    m = re.search(r"\b(x\d{3,4}[a-z]{0,3}(?:-[a-z0-9]+)?)\b", t, re.I)   # X540SA-XX004D / X552C
    if m:
        return m.group(1).upper()

    m = re.search(r"\b(fx\d{3,4}[a-z]{0,3})\b", t, re.I)                 # FX505 / FX506 etc
    if m:
        return m.group(1).upper()

    m = re.search(r"\b(tuf\s+fx\d{3,4}[a-z]{0,3})\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).upper()

    m = re.search(r"\b(zenbook\s+\d{2})\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()
    m = re.search(r"\b(zenbook)\b", t, re.I)
    if m:
        return "Zenbook"

    # ---------- Acer ----------
    m = re.search(r"\b(aspire\s+[a-z]?\d(?:-\d{3,4}[a-z]{0,3}|[a-z0-9]{3,6}))\b", t, re.I)  # Aspire V / E1-522 / 5935G
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()

    m = re.search(r"\b(extensa\s+\d{1,2})\b", t, re.I)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).title()
    m = re.search(r"\b(e1-\d{3})\b", t, re.I)
    if m:
        return m.group(1).upper()

    m = re.search(r"\b(aspire\s+v)\b", t, re.I)
    if m:
        return "Aspire V"

    # ---------- Medion / altele ----------
    m = re.search(r"\b(p\d{4})\b", t, re.I)                           # P6620
    if m and "quadro" not in t and "nvidia" not in t:
        return m.group(1).upper()

    # ---------- fallback cod alfanumeric ----------
    m = re.search(r"\b([a-z]{1,4}\d{2,5}[a-z]{0,4}(?:-\d{2,6}[a-z0-9]{0,4})?)\b", t, re.I)
    if m:
        cand = m.group(1).upper()
        if cand.lower() not in MODEL_STOP and len(cand) >= 3:
            return cand

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


def extract(text: str, regex: re.Pattern) -> str | None:
    m = regex.search(text or "")
    return m.group(0).strip() if m else None


def _is_laptop(source: str, title: str, desc: str) -> int:
    src = (source or "").lower()
    if src == "pcgarage":
        return 1

    t = (title or "").lower()
    d = (desc or "").lower()

    # 1) în titlu: semnale clare de non-laptop
    if any(k in t for k in NON_LAPTOP_KEYWORDS):
        return 0

    # 2) device-uri clar non-laptop (în titlu sau descriere)
    explicit_non_laptop = ["iphone", "telefon", "tablet", "tableta", "tabletă", "mac studio", "surface pro"]
    if any(k in t for k in explicit_non_laptop):
        return 0
    if any(k in d for k in ["mac studio", "surface pro", "chromebox", "mini pc"]):
        return 0
    
    # în _is_laptop(), înainte de return 1:
    if source.lower() == "publi24":
        # un laptop nu costă sub 100 RON
        pass  # poți valida asta la nivel de products_clean după
    
    # 3) pentru Publi24, dacă a trecut filtrul inițial, îl tratăm ca laptop;
    # nu mai penalizăm descrierea completă pentru cuvinte precum "încărcător" / "baterie"
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

    rows = cur.execute("""
        SELECT
            pc.rowid,
            pc.source,
            pc.url,
            pc.title_clean,
            pc.brand_guess,
            pc.model_guess,
            pc.condition_norm,
            p.description_text,
            p.specs_raw
        FROM products_clean pc
        LEFT JOIN products p
            ON p.url = pc.url
    """).fetchall()

    updated = 0
    for r in rows:
        source = (r["source"] or "")
        url = (r["url"] or "")
        title = (r["title_clean"] or "")
        desc = (r["description_text"] or "")
        raw_brand = r["brand_guess"]
        raw_model_guess = r["model_guess"]
        existing_cond = r["condition_norm"]

        raw_specs = r["specs_raw"]
        specs = None
        if raw_specs:
            try:
                specs = json.loads(raw_specs) if isinstance(raw_specs, str) else raw_specs
            except Exception:
                specs = None

        t_norm = normalize_title(title)
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
                m_norm = (
                    guess_model_from_pcgarage_url(url)
                    or guess_model_norm(raw_model_guess or "")
                    or guess_model_norm(t_norm)
                    or plausible_model_guess(raw_model_guess)
                )
            else:
                m_norm = (
                    guess_model_norm(raw_model_guess or "")
                    or guess_model_norm(t_norm)
                    or plausible_model_guess(raw_model_guess)
                )

        # condiție
        cond = normalize_condition(
            f"{title} {desc}",
            source=source,
            specs_raw=specs,
        )

        if source.lower() == "pcgarage":
            cond = "new"

        if not cond and existing_cond:
            cond = existing_cond

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