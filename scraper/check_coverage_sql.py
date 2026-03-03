import sqlite3
from pathlib import Path
from app.config.base import DB_PATH

BAD = (
    "Nu, mulțumesc",
    "Nu, multumesc",
    "Accept",
    "Acceptă",
    "Accepta",
    "Respinge",
    "Închide",
    "Inchide",
    "Setări",
    "Setari",
    "Preferințe",
    "Preferinte",
)

DB_PATH = Path(__file__).resolve().parent / "data_out" / "products.db"

QUERIES = {
    "coverage_by_source": """
        SELECT source,
               COUNT(*) as n,
               SUM(CASE WHEN model_guess IS NOT NULL THEN 1 ELSE 0 END) as model_ok,
               SUM(CASE WHEN location IS NOT NULL THEN 1 ELSE 0 END) as location_ok,
               SUM(CASE WHEN posted_at IS NOT NULL THEN 1 ELSE 0 END) as posted_ok
        FROM products_clean
        GROUP BY source
        ORDER BY n DESC;
    """,
    "pcgarage_missing_price_value": """
        SELECT COUNT(*) as missing_price_value
        FROM products
        WHERE source='pcgarage' AND price_value IS NULL;
    """,
    "latest_publi24": """
        SELECT posted_at, title, location, price_value, url
        FROM products
        WHERE source='publi24'
        ORDER BY posted_at DESC
        LIMIT 5;
    """,
}

def fix_bad_locations(conn):
    cur = conn.cursor()
    cur.execute(
        f"""
        UPDATE products
        SET location = NULL
        WHERE source='publi24' AND location IN ({",".join(["?"]*len(BAD))})
        """,
        BAD,
    )
    print("rows_fixed:", cur.rowcount)
    conn.commit()

def main():
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        fix_bad_locations(conn)
        for name, sql in QUERIES.items():
            print(f"\n=== {name} ===")
            rows = conn.execute(sql).fetchall()
            if not rows:
                print("(no rows)")
                continue
            # print rows
            for r in rows:
                print(dict(r))
    finally:
        conn.close()

if __name__ == "__main__":
    main()