import csv
import sqlite3
from pathlib import Path
from statistics import median

from app.config.base import DB_PATH

MIN_USED = 3
MIN_NEW = 3

EXPORT_DIR = Path("data_out/exports")
ROBUST_CSV = EXPORT_DIR / "robust_price_groups.csv"
EXPLORATORY_CSV = EXPORT_DIR / "exploratory_price_groups.csv"
DETAILED_CSV = EXPORT_DIR / "comparable_products_detailed.csv"


def median_or_none(values):
    return round(median(values), 2) if values else None


def ensure_export_dir():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def fetch_common_pairs(cur):
    return cur.execute("""
        WITH used_pairs AS (
            SELECT brand_norm, model_family
            FROM products_clean
            WHERE source = 'publi24'
              AND is_laptop = 1
              AND brand_norm IS NOT NULL
              AND model_family IS NOT NULL
            GROUP BY brand_norm, model_family
        ),
        new_pairs AS (
            SELECT brand_norm, model_family
            FROM products_clean
            WHERE source = 'pcgarage'
              AND is_laptop = 1
              AND brand_norm IS NOT NULL
              AND model_family IS NOT NULL
            GROUP BY brand_norm, model_family
        )
        SELECT u.brand_norm, u.model_family
        FROM used_pairs u
        INNER JOIN new_pairs n
            ON u.brand_norm = n.brand_norm
           AND u.model_family = n.model_family
        ORDER BY u.brand_norm, u.model_family
    """).fetchall()


def fetch_prices(cur, source, brand, family):
    rows = cur.execute("""
        SELECT price_ron
        FROM products_clean
        WHERE source = ?
          AND is_laptop = 1
          AND brand_norm = ?
          AND model_family = ?
          AND price_ron IS NOT NULL
    """, (source, brand, family)).fetchall()
    return [r["price_ron"] for r in rows]


def build_group_rows(cur):
    pairs = fetch_common_pairs(cur)
    all_rows = []

    for pair in pairs:
        brand = pair["brand_norm"]
        family = pair["model_family"]

        used_prices = fetch_prices(cur, "publi24", brand, family)
        new_prices = fetch_prices(cur, "pcgarage", brand, family)

        if not used_prices or not new_prices:
            continue

        used_med = median_or_none(used_prices)
        new_med = median_or_none(new_prices)

        ratio = round(used_med / new_med, 3) if used_med and new_med else None
        discount_pct = round((1 - used_med / new_med) * 100, 1) if used_med and new_med else None

        robust = (len(used_prices) >= MIN_USED) and (len(new_prices) >= MIN_NEW)

        all_rows.append({
            "brand_norm": brand,
            "model_family": family,
            "used_n": len(used_prices),
            "new_n": len(new_prices),
            "used_median_ron": used_med,
            "new_median_ron": new_med,
            "used_to_new_ratio": ratio,
            "discount_pct_vs_new": discount_pct,
            "robust_group": 1 if robust else 0,
        })

    all_rows.sort(
        key=lambda x: (x["robust_group"], x["used_n"] + x["new_n"], x["brand_norm"], x["model_family"]),
        reverse=True
    )
    return all_rows


def export_group_csv(path, rows):
    fieldnames = [
        "brand_norm",
        "model_family",
        "used_n",
        "new_n",
        "used_median_ron",
        "new_median_ron",
        "used_to_new_ratio",
        "discount_pct_vs_new",
        "robust_group",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def export_detailed_csv(cur, comparable_rows):
    if not comparable_rows:
        with DETAILED_CSV.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "source", "url", "title_clean", "brand_norm", "model_family", "model_norm",
                "title_std", "price_ron", "condition_norm", "cpu_guess", "ram_gb",
                "storage_guess", "gpu_guess", "screen_in", "robust_group"
            ])
        return

    pair_set = {(r["brand_norm"], r["model_family"]): r["robust_group"] for r in comparable_rows}

    rows = cur.execute("""
        SELECT
            source,
            url,
            title_clean,
            brand_norm,
            model_family,
            model_norm,
            title_std,
            price_ron,
            condition_norm,
            cpu_guess,
            ram_gb,
            storage_guess,
            gpu_guess,
            screen_in
        FROM products_clean
        WHERE is_laptop = 1
          AND brand_norm IS NOT NULL
          AND model_family IS NOT NULL
        ORDER BY source, brand_norm, model_family, price_ron
    """).fetchall()

    fieldnames = [
        "source", "url", "title_clean", "brand_norm", "model_family", "model_norm",
        "title_std", "price_ron", "condition_norm", "cpu_guess", "ram_gb",
        "storage_guess", "gpu_guess", "screen_in", "robust_group"
    ]

    with DETAILED_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for r in rows:
            key = (r["brand_norm"], r["model_family"])
            if key not in pair_set:
                continue

            writer.writerow({
                "source": r["source"],
                "url": r["url"],
                "title_clean": r["title_clean"],
                "brand_norm": r["brand_norm"],
                "model_family": r["model_family"],
                "model_norm": r["model_norm"],
                "title_std": r["title_std"],
                "price_ron": r["price_ron"],
                "condition_norm": r["condition_norm"],
                "cpu_guess": r["cpu_guess"],
                "ram_gb": r["ram_gb"],
                "storage_guess": r["storage_guess"],
                "gpu_guess": r["gpu_guess"],
                "screen_in": r["screen_in"],
                "robust_group": pair_set[key],
            })


def main():
    ensure_export_dir()

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    all_rows = build_group_rows(cur)
    robust_rows = [r for r in all_rows if r["robust_group"] == 1]
    exploratory_rows = [r for r in all_rows if r["robust_group"] == 0]

    export_group_csv(ROBUST_CSV, robust_rows)
    export_group_csv(EXPLORATORY_CSV, exploratory_rows)
    export_detailed_csv(cur, all_rows)

    print("=== EXPORT PRICE COMPARABILITY ===")
    print("DB_PATH:", DB_PATH)
    print(f"robustness threshold: used_n >= {MIN_USED}, new_n >= {MIN_NEW}")
    print()
    print("robust groups exported:", len(robust_rows))
    print("exploratory groups exported:", len(exploratory_rows))
    print("all comparable groups:", len(all_rows))
    print()
    print("wrote:", ROBUST_CSV)
    print("wrote:", EXPLORATORY_CSV)
    print("wrote:", DETAILED_CSV)

    conn.close()


if __name__ == "__main__":
    main()