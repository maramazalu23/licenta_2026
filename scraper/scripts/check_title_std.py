import sqlite3
from app.config.base import DB_PATH

def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    n = cur.execute("SELECT COUNT(*) AS n FROM products_clean WHERE is_laptop=1").fetchone()["n"]
    n_std = cur.execute("SELECT COUNT(*) AS n FROM products_clean WHERE is_laptop=1 AND title_std IS NOT NULL").fetchone()["n"]
    n_fam = cur.execute("SELECT COUNT(*) AS n FROM products_clean WHERE is_laptop=1 AND model_family IS NOT NULL").fetchone()["n"]

    print("laptops:", n)
    print("with_title_std:", n_std)
    print("with_model_family:", n_fam)
    print("\nSAMPLES:\n")

    rows = cur.execute("""
        SELECT source, title_norm, model_norm, model_family, title_std, url
        FROM products_clean
        WHERE is_laptop=1
        ORDER BY RANDOM()
        LIMIT 12
    """).fetchall()

    for r in rows:
        print(f"{r['source']} | model_norm={r['model_norm']} | family={r['model_family']}")
        print("  title_norm:", r["title_norm"])
        print("  title_std :", r["title_std"])
        print("  url      :", r["url"])
        print()

    conn.close()

if __name__ == "__main__":
    main()