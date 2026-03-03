import sqlite3
from app.config.base import DB_PATH

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# 1) coloane existente
cols = [r["name"] for r in cur.execute("PRAGMA table_info(products_clean)").fetchall()]
need = ["brand_norm","condition_norm","cpu_guess","ram_gb","storage_guess","gpu_guess","screen_in"]
print("missing_cols:", [c for c in need if c not in cols])

# 2) coverage
row = cur.execute("""
SELECT
  COUNT(*) AS n,
  SUM(CASE WHEN brand_norm IS NOT NULL THEN 1 ELSE 0 END) AS brand_ok,
  SUM(CASE WHEN condition_norm IS NOT NULL THEN 1 ELSE 0 END) AS cond_ok,
  SUM(CASE WHEN cpu_guess IS NOT NULL THEN 1 ELSE 0 END) AS cpu_ok,
  SUM(CASE WHEN ram_gb IS NOT NULL THEN 1 ELSE 0 END) AS ram_ok,
  SUM(CASE WHEN storage_guess IS NOT NULL THEN 1 ELSE 0 END) AS storage_ok,
  SUM(CASE WHEN gpu_guess IS NOT NULL THEN 1 ELSE 0 END) AS gpu_ok,
  SUM(CASE WHEN screen_in IS NOT NULL THEN 1 ELSE 0 END) AS screen_ok
FROM products_clean
WHERE is_laptop = 1
""").fetchone()

print("n:", row["n"])
print("coverage:", dict(row))

# 3) pe surse (ca să vezi diferența publi24 vs pcgarage)
rows = cur.execute("""
SELECT source,
  COUNT(*) n,
  SUM(brand_norm IS NOT NULL) brand_ok,
  SUM(condition_norm IS NOT NULL) cond_ok,
  SUM(cpu_guess IS NOT NULL) cpu_ok,
  SUM(ram_gb IS NOT NULL) ram_ok,
  SUM(storage_guess IS NOT NULL) storage_ok,
  SUM(gpu_guess IS NOT NULL) gpu_ok,
  SUM(screen_in IS NOT NULL) screen_ok
FROM products_clean
WHERE is_laptop = 1
GROUP BY source
""").fetchall()
for r in rows:
  print(dict(r))

row = cur.execute("""
SELECT COUNT(*)
FROM products_clean
WHERE is_laptop=1 AND model_norm IS NOT NULL
""").fetchone()

print("model_norm_count:", row[0])

conn.close()