import sqlite3
from app.config.base import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
c = conn.cursor()

print("=== products (raw) ===")
rows = c.execute("""
    SELECT price, price_value
    FROM products
    WHERE source = 'pcgarage'
      AND price_value IS NOT NULL
    LIMIT 5
""").fetchall()

for r in rows:
    print(r["price"], r["price_value"])

print("\n=== products_clean ===")
rows2 = c.execute("""
    SELECT price_ron, currency
    FROM products_clean
    WHERE source = 'pcgarage'
      AND price_ron IS NOT NULL
    LIMIT 5
""").fetchall()

for r in rows2:
    print(r["price_ron"], r["currency"])

conn.close()