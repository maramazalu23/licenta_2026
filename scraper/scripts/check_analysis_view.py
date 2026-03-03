# scripts/check_analysis_view.py
import sqlite3
from app.config.base import DB_PATH

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    n = cur.execute("SELECT COUNT(*) FROM products_analysis").fetchone()[0]
    print("products_analysis rows:", n)

    # probe: verifică că există price_value
    row = cur.execute("""
        SELECT source, price_value, currency, title_std
        FROM products_analysis
        LIMIT 5
    """).fetchall()
    for r in row:
        print(r)

    conn.close()

if __name__ == "__main__":
    main()