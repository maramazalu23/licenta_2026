# scripts/create_products_analysis_view.py
import sqlite3
from app.config.base import DB_PATH

SQL = """
DROP VIEW IF EXISTS products_analysis;

CREATE VIEW products_analysis AS
SELECT
  rowid AS clean_rowid,
  source,
  url,

  -- titluri
  COALESCE(title_norm, title_clean) AS title_norm,
  title_std,

  -- normalizări
  brand_norm,
  model_norm,
  model_family,
  condition_norm,

  -- spec guesses
  cpu_guess,
  ram_gb,
  storage_guess,
  gpu_guess,
  screen_in,

  -- PRET: în tabela ta e price_ron, NU price
  price_ron AS price_value,
  currency,

  -- dates/loc: în tabela ta sunt *_utc și *_clean
  posted_at_utc AS posted_at,
  location_clean AS location,
  county,
  city

FROM products_clean
WHERE is_laptop = 1;
"""

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.executescript(SQL)
    conn.commit()
    conn.close()
    print("products_analysis view: OK")

if __name__ == "__main__":
    main()