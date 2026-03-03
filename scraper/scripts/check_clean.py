import sqlite3
from app.config.base import DB_PATH

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='products_clean'")
print("has_products_clean:", cur.fetchone() is not None)

cur.execute("SELECT COUNT(*) FROM products_clean")
print("products_clean:", cur.fetchone()[0])

cur.execute("SELECT source, COUNT(*) FROM products_clean GROUP BY source")
print("by_source:", cur.fetchall())

conn.close()