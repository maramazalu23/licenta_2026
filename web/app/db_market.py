import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR.parent
ROOT_DIR = WEB_DIR.parent
PRODUCTS_DB_PATH = ROOT_DIR / "scraper" / "data_out" / "products.db"

BAD_TITLE_TOKENS = [
    "dezmembrare",
    "dezmembrez",
    "dezmembrare laptop",
    "piese",
    "piesa",
    "wireless card",
    "wifi link",
    "card wifi",
    "incarcator",
    "încărcător",
    "alimentator",
    "ssd ",
    " hdd",
    "memorie usb",
    "usb",
    "placa de baza",
    "placă de bază",
    "display",
    "ecran",
    "tastatura",
    "tastatură",
    "mouse",
    "baterie externa",
    "acumulator extern",
    "laptop de vanzare",
    "laptop de vânzare",
    "laptop si",
    "laptop și",
]

BAD_TITLE_EQUALS = [
    "ssd samsung de 120 gb",
]

def _dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def _get_conn():
    if not PRODUCTS_DB_PATH.exists():
        raise FileNotFoundError(f"products.db not found at: {PRODUCTS_DB_PATH}")

    conn = sqlite3.connect(f"file:{PRODUCTS_DB_PATH}?mode=ro", uri=True)
    conn.row_factory = _dict_factory
    return conn


def _clean_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value if value else None


def _normalize_condition(condition: Optional[str]) -> Optional[str]:
    condition = _clean_str(condition)
    if not condition:
        return None

    c = condition.lower()
    if c in {"new", "nou", "sigilat"}:
        return "new"
    if c in {"used", "second hand", "second-hand", "sh"}:
        return "used"
    return c


def _normalize_int(value: Optional[Any]) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def _base_visibility_clauses():
    clauses = [
        "is_laptop = 1",
        "price_ron IS NOT NULL",
        "title_clean IS NOT NULL",
        "TRIM(title_clean) != ''",
    ]
    params: List[Any] = []

    for token in BAD_TITLE_TOKENS:
        clauses.append("LOWER(title_clean) NOT LIKE ?")
        params.append(f"%{token.lower()}%")

    for exact_title in BAD_TITLE_EQUALS:
        clauses.append("LOWER(TRIM(title_clean)) != ?")
        params.append(exact_title.lower())

    return clauses, params


def _fetch_all(query: str, params: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    params = params or []
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        return cur.fetchall()


def _fetch_one(query: str, params: Optional[List[Any]] = None) -> Optional[Dict[str, Any]]:
    params = params or []
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        return cur.fetchone()


def _percentile(values: List[float], p: float) -> Optional[float]:
    if not values:
        return None

    xs = sorted(float(v) for v in values if v is not None)
    if not xs:
        return None

    if len(xs) == 1:
        return round(xs[0], 2)

    k = (len(xs) - 1) * p
    f = int(k)
    c = min(f + 1, len(xs) - 1)

    if f == c:
        return round(xs[f], 2)

    d0 = xs[f] * (c - k)
    d1 = xs[c] * (k - f)
    return round(d0 + d1, 2)


def _compute_stats(values: List[float]) -> Dict[str, Optional[float]]:
    if not values:
        return {
            "n": 0,
            "min": None,
            "q1": None,
            "median": None,
            "q3": None,
            "max": None,
        }

    xs = [float(v) for v in values if v is not None]
    if not xs:
        return {
            "n": 0,
            "min": None,
            "q1": None,
            "median": None,
            "q3": None,
            "max": None,
        }

    return {
        "n": len(xs),
        "min": round(min(xs), 2),
        "q1": _percentile(xs, 0.25),
        "median": _percentile(xs, 0.50),
        "q3": _percentile(xs, 0.75),
        "max": round(max(xs), 2),
    }


def _build_where_clauses(
    brand: Optional[str] = None,
    ram_gb: Optional[int] = None,
    model_family: Optional[str] = None,
    condition: Optional[str] = None,
    source: Optional[str] = None,
):
    clauses, params = _base_visibility_clauses()

    brand = _clean_str(brand)
    model_family = _clean_str(model_family)
    source = _clean_str(source)
    ram_gb = _normalize_int(ram_gb)
    condition = _normalize_condition(condition)

    if brand:
        clauses.append("brand_norm = ?")
        params.append(brand)

    if ram_gb is not None:
        clauses.append("ram_gb = ?")
        params.append(ram_gb)

    if model_family:
        clauses.append("model_family = ?")
        params.append(model_family)

    if condition:
        clauses.append("condition_norm = ?")
        params.append(condition)

    if source:
        clauses.append("source = ?")
        params.append(source)

    return clauses, params


def _row_to_product(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "url": row.get("url"),
        "source": row.get("source"),
        "title": row.get("title_clean"),
        "brand": row.get("brand_norm"),
        "model": row.get("model_norm"),
        "model_family": row.get("model_family"),
        "cpu": row.get("cpu_guess"),
        "ram_gb": _normalize_int(row.get("ram_gb")),
        "storage": row.get("storage_guess"),
        "gpu": row.get("gpu_guess"),
        "screen_in": row.get("screen_in"),
        "condition": row.get("condition_norm"),
        "price_ron": row.get("price_ron"),
        "city": row.get("city"),
        "county": row.get("county"),
    }


def get_market_summary() -> Dict[str, Any]:
    clauses, params = _base_visibility_clauses()

    query = f"""
        SELECT
            COUNT(*) AS total_products,
            SUM(CASE WHEN condition_norm = 'used' THEN 1 ELSE 0 END) AS used_count,
            SUM(CASE WHEN condition_norm = 'new' THEN 1 ELSE 0 END) AS new_count,
            COUNT(DISTINCT brand_norm) AS distinct_brands,
            MIN(price_ron) AS min_price_ron,
            MAX(price_ron) AS max_price_ron
        FROM products_clean
        WHERE {' AND '.join(clauses)}
    """
    row = _fetch_one(query, params) or {}

    return {
        "total_products": row.get("total_products", 0) or 0,
        "used_count": row.get("used_count", 0) or 0,
        "new_count": row.get("new_count", 0) or 0,
        "distinct_brands": row.get("distinct_brands", 0) or 0,
        "min_price_ron": row.get("min_price_ron"),
        "max_price_ron": row.get("max_price_ron"),
    }


def get_price_stats(
    brand: Optional[str] = None,
    ram_gb: Optional[int] = None,
    model_family: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Returneaza statistici de pret pentru segmentul cerut.
    Fallback:
    1. brand + ram + family
    2. brand + ram
    3. brand + family
    4. brand
    5. ram
    """

    fallback_chain = [
        {
            "label": "brand+ram+family",
            "brand": brand,
            "ram_gb": ram_gb,
            "model_family": model_family,
        },
        {
            "label": "brand+ram",
            "brand": brand,
            "ram_gb": ram_gb,
            "model_family": None,
        },
        {
            "label": "brand+family",
            "brand": brand,
            "ram_gb": None,
            "model_family": model_family,
        },
        {
            "label": "brand",
            "brand": brand,
            "ram_gb": None,
            "model_family": None,
        },
        {
            "label": "ram",
            "brand": None,
            "ram_gb": ram_gb,
            "model_family": None,
        },
    ]

    for step in fallback_chain:
        used_clauses, used_params = _build_where_clauses(
            brand=step["brand"],
            ram_gb=step["ram_gb"],
            model_family=step["model_family"],
            condition="used",
        )
        new_clauses, new_params = _build_where_clauses(
            brand=step["brand"],
            ram_gb=step["ram_gb"],
            model_family=step["model_family"],
            condition="new",
        )

        used_query = f"""
            SELECT price_ron
            FROM products_clean
            WHERE {' AND '.join(used_clauses)}
        """
        new_query = f"""
            SELECT price_ron
            FROM products_clean
            WHERE {' AND '.join(new_clauses)}
        """

        used_rows = _fetch_all(used_query, used_params)
        new_rows = _fetch_all(new_query, new_params)

        used_prices = [float(r["price_ron"]) for r in used_rows if r.get("price_ron") is not None]
        new_prices = [float(r["price_ron"]) for r in new_rows if r.get("price_ron") is not None]

        if len(used_prices) >= 3:
            used_stats = _compute_stats(used_prices)
            new_stats = _compute_stats(new_prices)

            return {
                "source_level": step["label"],
                "filters_used": {
                    "brand": step["brand"],
                    "ram_gb": _normalize_int(step["ram_gb"]),
                    "model_family": step["model_family"],
                },
                "used": {
                    "n": used_stats["n"],
                    "q1": used_stats["q1"],
                    "median": used_stats["median"],
                    "q3": used_stats["q3"],
                },
                "new": {
                    "n": new_stats["n"],
                    "median": new_stats["median"],
                },
            }

    return {
        "source_level": "no_match",
        "filters_used": {
            "brand": _clean_str(brand),
            "ram_gb": _normalize_int(ram_gb),
            "model_family": _clean_str(model_family),
        },
        "used": {
            "n": 0,
            "q1": None,
            "median": None,
            "q3": None,
        },
        "new": {
            "n": 0,
            "median": None,
        },
    }


def get_similar_products(
    brand: Optional[str] = None,
    ram_gb: Optional[int] = None,
    model_family: Optional[str] = None,
    limit: int = 12,
) -> List[Dict[str, Any]]:
    """
    Returneaza produse similare cu un scor simplu de apropiere.
    Sunt pastrate doar rezultatele cu similarity_score > 0.
    """

    brand = _clean_str(brand)
    model_family = _clean_str(model_family)
    ram_gb = _normalize_int(ram_gb)
    limit = max(1, min(int(limit), 50))

    score_parts = []
    score_params: List[Any] = []

    if brand:
        score_parts.append("CASE WHEN brand_norm = ? THEN 3 ELSE 0 END")
        score_params.append(brand)
    else:
        score_parts.append("0")

    if model_family:
        score_parts.append("CASE WHEN model_family = ? THEN 4 ELSE 0 END")
        score_params.append(model_family)
    else:
        score_parts.append("0")

    if ram_gb is not None:
        score_parts.append("CASE WHEN ram_gb = ? THEN 2 ELSE 0 END")
        score_params.append(ram_gb)
    else:
        score_parts.append("0")

    score_expr = " + ".join(score_parts)

    base_clauses, base_params = _base_visibility_clauses()

    query = f"""
        SELECT
            url,
            source,
            title_clean,
            brand_norm,
            model_norm,
            model_family,
            cpu_guess,
            ram_gb,
            storage_guess,
            gpu_guess,
            screen_in,
            condition_norm,
            price_ron,
            city,
            county,
            ({score_expr}) AS similarity_score
        FROM products_clean
        WHERE {' AND '.join(base_clauses)}
          AND ({score_expr}) > 0
        ORDER BY similarity_score DESC, price_ron ASC
        LIMIT ?
    """

    params = score_params + base_params + score_params + [limit]
    rows = _fetch_all(query, params)

    results = []
    for row in rows:
        item = _row_to_product(row)
        item["similarity_score"] = row.get("similarity_score", 0)
        results.append(item)

    return results


def get_explore_filters() -> Dict[str, List[Any]]:
    base_clauses, base_params = _base_visibility_clauses()
    where_sql = " AND ".join(base_clauses)

    brands = _fetch_all(f"""
        SELECT DISTINCT brand_norm
        FROM products_clean
        WHERE {where_sql}
          AND brand_norm IS NOT NULL
          AND TRIM(brand_norm) != ''
        ORDER BY brand_norm
    """, base_params)

    families = _fetch_all(f"""
        SELECT DISTINCT model_family
        FROM products_clean
        WHERE {where_sql}
          AND model_family IS NOT NULL
          AND TRIM(model_family) != ''
        ORDER BY model_family
    """, base_params)

    rams = _fetch_all(f"""
        SELECT DISTINCT ram_gb
        FROM products_clean
        WHERE {where_sql}
          AND ram_gb IS NOT NULL
        ORDER BY ram_gb
    """, base_params)

    sources = _fetch_all(f"""
        SELECT DISTINCT source
        FROM products_clean
        WHERE {where_sql}
          AND source IS NOT NULL
          AND TRIM(source) != ''
        ORDER BY source
    """, base_params)

    return {
        "brands": [r["brand_norm"] for r in brands],
        "families": [r["model_family"] for r in families],
        "ram_options": [_normalize_int(r["ram_gb"]) for r in rams if r.get("ram_gb") is not None],
        "conditions": ["new", "used"],
        "sources": [r["source"] for r in sources],
    }


def get_explore_products(
    brand: Optional[str] = None,
    family: Optional[str] = None,
    ram: Optional[int] = None,
    condition: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 60,
) -> Dict[str, Any]:
    limit = max(1, min(int(limit), 200))

    clauses, params = _build_where_clauses(
        brand=brand,
        ram_gb=ram,
        model_family=family,
        condition=condition,
        source=source,
    )

    query = f"""
        SELECT
            url,
            source,
            title_clean,
            brand_norm,
            model_norm,
            model_family,
            cpu_guess,
            ram_gb,
            storage_guess,
            gpu_guess,
            screen_in,
            condition_norm,
            price_ron,
            city,
            county
        FROM products_clean
        WHERE {' AND '.join(clauses)}
        ORDER BY price_ron ASC
        LIMIT ?
    """
    params.append(limit)

    rows = _fetch_all(query, params)
    products = [_row_to_product(row) for row in rows]
    prices = [float(p["price_ron"]) for p in products if p.get("price_ron") is not None]
    stats = _compute_stats(prices)

    return {
        "filters_used": {
            "brand": _clean_str(brand),
            "family": _clean_str(family),
            "ram": _normalize_int(ram),
            "condition": _normalize_condition(condition),
            "source": _clean_str(source),
        },
        "count": len(products),
        "stats": {
            "min": stats["min"],
            "q1": stats["q1"],
            "median": stats["median"],
            "q3": stats["q3"],
            "max": stats["max"],
        },
        "products": products,
    }


if __name__ == "__main__":
    print("=== MARKET SUMMARY ===")
    print(get_market_summary())

    print("\n=== EXPLORE FILTERS ===")
    filters = get_explore_filters()
    print({
        "brands_sample": filters["brands"][:10],
        "families_sample": filters["families"][:10],
        "ram_options": filters["ram_options"][:10],
        "sources": filters["sources"],
    })

    print("\n=== PRICE STATS EXAMPLE ===")
    print(get_price_stats(brand="Lenovo", ram_gb=16, model_family="ThinkBook"))

    print("\n=== SIMILAR PRODUCTS EXAMPLE ===")
    similars = get_similar_products(brand="Lenovo", ram_gb=16, model_family="ThinkBook", limit=5)
    for item in similars:
        print(item)

    print("\n=== EXPLORE PRODUCTS EXAMPLE ===")
    sample = get_explore_products(brand="Dell", condition="used", limit=5)
    print(f"count={sample['count']}")
    for item in sample["products"]:
        print(item)