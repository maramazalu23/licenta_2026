import sqlite3
from app.config.base import DB_PATH


def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    print("=== COMPATIBILITY CHECK ===")
    print("DB_PATH:", DB_PATH)
    print()

    # doar laptopuri
    total = cur.execute("""
        SELECT COUNT(*)
        FROM products_clean
        WHERE is_laptop = 1
    """).fetchone()[0]

    by_source = cur.execute("""
        SELECT source, COUNT(*)
        FROM products_clean
        WHERE is_laptop = 1
        GROUP BY source
        ORDER BY source
    """).fetchall()

    print("laptops total:", total)
    print("laptops by source:", by_source)
    print()

    # 1) overlap pe brand
    rows = cur.execute("""
        WITH used_brands AS (
            SELECT DISTINCT brand_norm
            FROM products_clean
            WHERE source = 'publi24'
              AND is_laptop = 1
              AND brand_norm IS NOT NULL
        ),
        new_brands AS (
            SELECT DISTINCT brand_norm
            FROM products_clean
            WHERE source = 'pcgarage'
              AND is_laptop = 1
              AND brand_norm IS NOT NULL
        )
        SELECT u.brand_norm
        FROM used_brands u
        INNER JOIN new_brands n
            ON u.brand_norm = n.brand_norm
        ORDER BY u.brand_norm
    """).fetchall()

    common_brands = [r[0] for r in rows]
    print("common brands:", common_brands)
    print("common brand count:", len(common_brands))
    print()

    # 2) overlap pe brand + family
    rows = cur.execute("""
        WITH used_pairs AS (
            SELECT brand_norm, model_family, COUNT(*) AS used_count
            FROM products_clean
            WHERE source = 'publi24'
              AND is_laptop = 1
              AND brand_norm IS NOT NULL
              AND model_family IS NOT NULL
            GROUP BY brand_norm, model_family
        ),
        new_pairs AS (
            SELECT brand_norm, model_family, COUNT(*) AS new_count
            FROM products_clean
            WHERE source = 'pcgarage'
              AND is_laptop = 1
              AND brand_norm IS NOT NULL
              AND model_family IS NOT NULL
            GROUP BY brand_norm, model_family
        )
        SELECT
            u.brand_norm,
            u.model_family,
            u.used_count,
            n.new_count
        FROM used_pairs u
        INNER JOIN new_pairs n
            ON u.brand_norm = n.brand_norm
           AND u.model_family = n.model_family
        ORDER BY u.brand_norm, u.model_family
    """).fetchall()

    print("=== COMMON brand_norm + model_family ===")
    for r in rows:
        print(r)
    print("common family pairs:", len(rows))
    print()

    # 3) overlap pe model exact
    rows = cur.execute("""
        WITH used_models AS (
            SELECT brand_norm, model_norm, COUNT(*) AS used_count
            FROM products_clean
            WHERE source = 'publi24'
              AND is_laptop = 1
              AND brand_norm IS NOT NULL
              AND model_norm IS NOT NULL
            GROUP BY brand_norm, model_norm
        ),
        new_models AS (
            SELECT brand_norm, model_norm, COUNT(*) AS new_count
            FROM products_clean
            WHERE source = 'pcgarage'
              AND is_laptop = 1
              AND brand_norm IS NOT NULL
              AND model_norm IS NOT NULL
            GROUP BY brand_norm, model_norm
        )
        SELECT
            u.brand_norm,
            u.model_norm,
            u.used_count,
            n.new_count
        FROM used_models u
        INNER JOIN new_models n
            ON u.brand_norm = n.brand_norm
           AND u.model_norm = n.model_norm
        ORDER BY u.brand_norm, u.model_norm
    """).fetchall()

    print("=== COMMON brand_norm + model_norm ===")
    for r in rows:
        print(r)
    print("common exact model pairs:", len(rows))
    print()

    # 4) summary pentru utilizare in licenta
    used_brand_family = cur.execute("""
        SELECT COUNT(*)
        FROM products_clean
        WHERE source = 'publi24'
          AND is_laptop = 1
          AND (brand_norm, model_family) IN (
              SELECT DISTINCT u.brand_norm, u.model_family
              FROM products_clean u
              JOIN products_clean n
                ON u.brand_norm = n.brand_norm
               AND u.model_family = n.model_family
             WHERE u.source = 'publi24'
               AND n.source = 'pcgarage'
               AND u.is_laptop = 1
               AND n.is_laptop = 1
               AND u.brand_norm IS NOT NULL
               AND u.model_family IS NOT NULL
          )
    """).fetchone()[0]

    new_brand_family = cur.execute("""
        SELECT COUNT(*)
        FROM products_clean
        WHERE source = 'pcgarage'
          AND is_laptop = 1
          AND (brand_norm, model_family) IN (
              SELECT DISTINCT u.brand_norm, u.model_family
              FROM products_clean u
              JOIN products_clean n
                ON u.brand_norm = n.brand_norm
               AND u.model_family = n.model_family
             WHERE u.source = 'publi24'
               AND n.source = 'pcgarage'
               AND u.is_laptop = 1
               AND n.is_laptop = 1
               AND u.brand_norm IS NOT NULL
               AND u.model_family IS NOT NULL
          )
    """).fetchone()[0]

    used_total = cur.execute("""
        SELECT COUNT(*)
        FROM products_clean
        WHERE source = 'publi24' AND is_laptop = 1
    """).fetchone()[0]

    new_total = cur.execute("""
        SELECT COUNT(*)
        FROM products_clean
        WHERE source = 'pcgarage' AND is_laptop = 1
    """).fetchone()[0]

    print("=== MATCHING COVERAGE ===")
    print(f"publi24 usable via brand+family: {used_brand_family}/{used_total} = {used_brand_family / used_total:.1%}")
    print(f"pcgarage usable via brand+family: {new_brand_family}/{new_total} = {new_brand_family / new_total:.1%}")

    conn.close()


if __name__ == "__main__":
    main()