import sqlite3
from statistics import median
from app.config.base import DB_PATH

MIN_USED = 3
MIN_NEW = 3


def median_or_none(values):
    return round(median(values), 2) if values else None


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    print("=== PRICE COMPARABILITY CHECK ===")
    print("DB_PATH:", DB_PATH)
    print(f"robustness threshold: used_n >= {MIN_USED}, new_n >= {MIN_NEW}")
    print()

    # toate perechile comune brand + family
    pairs = cur.execute("""
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

    if not pairs:
        print("No common brand+family pairs found.")
        conn.close()
        return

    all_rows = []

    for pair in pairs:
        brand = pair["brand_norm"]
        family = pair["model_family"]

        used_prices = [
            r["price_ron"] for r in cur.execute("""
                SELECT price_ron
                FROM products_clean
                WHERE source = 'publi24'
                  AND is_laptop = 1
                  AND brand_norm = ?
                  AND model_family = ?
                  AND price_ron IS NOT NULL
            """, (brand, family)).fetchall()
        ]

        new_prices = [
            r["price_ron"] for r in cur.execute("""
                SELECT price_ron
                FROM products_clean
                WHERE source = 'pcgarage'
                  AND is_laptop = 1
                  AND brand_norm = ?
                  AND model_family = ?
                  AND price_ron IS NOT NULL
            """, (brand, family)).fetchall()
        ]

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
            "robust": robust,
        })

    # sortare: întâi grupele robuste, apoi după volum total
    all_rows.sort(
        key=lambda x: (x["robust"], x["used_n"] + x["new_n"], x["brand_norm"], x["model_family"]),
        reverse=True
    )

    robust_rows = [r for r in all_rows if r["robust"]]
    exploratory_rows = [r for r in all_rows if not r["robust"]]

    print("=== ROBUST GROUPS ===")
    if robust_rows:
        for r in robust_rows:
            print(
                f"{r['brand_norm']} | {r['model_family']} | "
                f"used_n={r['used_n']} | new_n={r['new_n']} | "
                f"used_median={r['used_median_ron']} | new_median={r['new_median_ron']} | "
                f"ratio={r['used_to_new_ratio']} | discount={r['discount_pct_vs_new']}%"
            )
    else:
        print("No robust groups found.")
    print()

    print("=== EXPLORATORY GROUPS ===")
    if exploratory_rows:
        for r in exploratory_rows:
            print(
                f"{r['brand_norm']} | {r['model_family']} | "
                f"used_n={r['used_n']} | new_n={r['new_n']} | "
                f"used_median={r['used_median_ron']} | new_median={r['new_median_ron']} | "
                f"ratio={r['used_to_new_ratio']} | discount={r['discount_pct_vs_new']}%"
            )
    else:
        print("No exploratory groups found.")
    print()

    print("robust groups:", len(robust_rows))
    print("exploratory groups:", len(exploratory_rows))
    print("all comparable groups:", len(all_rows))
    print()

    # agregat doar pe grupele robuste
    robust_used = []
    robust_new = []

    for r in robust_rows:
        brand = r["brand_norm"]
        family = r["model_family"]

        robust_used.extend([
            x["price_ron"] for x in cur.execute("""
                SELECT price_ron
                FROM products_clean
                WHERE source = 'publi24'
                  AND is_laptop = 1
                  AND brand_norm = ?
                  AND model_family = ?
                  AND price_ron IS NOT NULL
            """, (brand, family)).fetchall()
        ])

        robust_new.extend([
            x["price_ron"] for x in cur.execute("""
                SELECT price_ron
                FROM products_clean
                WHERE source = 'pcgarage'
                  AND is_laptop = 1
                  AND brand_norm = ?
                  AND model_family = ?
                  AND price_ron IS NOT NULL
            """, (brand, family)).fetchall()
        ])

    print("=== AGGREGATE OVER ROBUST GROUPS ===")
    if robust_used and robust_new:
        used_med_all = round(median(robust_used), 2)
        new_med_all = round(median(robust_new), 2)
        ratio_all = round(used_med_all / new_med_all, 3)
        discount_all = round((1 - used_med_all / new_med_all) * 100, 1)

        print("used obs:", len(robust_used))
        print("new obs:", len(robust_new))
        print("used median ron:", used_med_all)
        print("new median ron:", new_med_all)
        print("used/new ratio:", ratio_all)
        print("discount vs new:", f"{discount_all}%")
    else:
        print("No robust aggregate available.")

    conn.close()


if __name__ == "__main__":
    main()