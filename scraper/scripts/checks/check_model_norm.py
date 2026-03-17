import sqlite3

conn = sqlite3.connect("data_out/products.db")
cur = conn.cursor()

print("=== COVERAGE IN products_clean ===")
queries = [
    ("title_std", "SELECT COUNT(*) FROM products_clean WHERE title_std IS NOT NULL"),
    ("model_norm", "SELECT COUNT(*) FROM products_clean WHERE model_norm IS NOT NULL"),
    ("brand_norm", "SELECT COUNT(*) FROM products_clean WHERE brand_norm IS NOT NULL"),
    ("cpu_guess", "SELECT COUNT(*) FROM products_clean WHERE cpu_guess IS NOT NULL"),
    ("ram_gb", "SELECT COUNT(*) FROM products_clean WHERE ram_gb IS NOT NULL"),
    ("storage_guess", "SELECT COUNT(*) FROM products_clean WHERE storage_guess IS NOT NULL"),
    ("gpu_guess", "SELECT COUNT(*) FROM products_clean WHERE gpu_guess IS NOT NULL"),
    ("screen_in", "SELECT COUNT(*) FROM products_clean WHERE screen_in IS NOT NULL"),
]

total = cur.execute("SELECT COUNT(*) FROM products_clean").fetchone()[0]
print("total:", total)

for name, q in queries:
    n = cur.execute(q).fetchone()[0]
    print(f"{name}: {n}/{total} = {round(100*n/total, 1)}%")

print("\n=== model_norm missing by source ===")
rows = cur.execute("""
SELECT source, COUNT(*)
FROM products_clean
WHERE model_norm IS NULL
GROUP BY source
""").fetchall()

for r in rows:
    print(r)

conn.close()