import sqlite3
from app.config.base import DB_PATH

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM products_clean WHERE is_laptop=1")
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM products_clean WHERE is_laptop=1 AND model_norm IS NOT NULL")
    with_model = cur.fetchone()[0]

    print("laptops:", total)
    print("laptops_with_model_norm:", with_model)

    # top lipsă model ca să vedem pattern-urile
    cur.execute("""
        SELECT source, title_norm, url
        FROM products_clean
        WHERE is_laptop=1 AND model_norm IS NULL
        ORDER BY source
        LIMIT 15
    """)
    rows = cur.fetchall()
    print("\nmissing_model_samples:")
    for s, t, u in rows:
        print(f"- {s} | {t}\n  {u}\n")

    n = cur.execute(
        "SELECT COUNT(*) FROM products_clean WHERE is_laptop=1 AND model_norm IS NOT NULL"
    ).fetchone()[0]
    print("model_norm_count:", n)

    conn.close()

if __name__ == "__main__":
    main()