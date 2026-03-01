from __future__ import annotations

import json
import os
import sqlite3
from typing import Iterable, Optional, Tuple

from app.config.base import DB_PATH
from app.models import Product


DDL_PRODUCTS = """
CREATE TABLE IF NOT EXISTS products (
  id INTEGER PRIMARY KEY AUTOINCREMENT,

  source TEXT NOT NULL,
  category TEXT NOT NULL,
  url TEXT NOT NULL UNIQUE,
  scraped_at TEXT NOT NULL,
  scrape_run_id TEXT,

  title TEXT NOT NULL,
  price TEXT,
  price_value REAL,
  currency TEXT,
  availability TEXT,
  location TEXT,
  posted_at TEXT,
  condition TEXT,

  description_text TEXT,
  description_html TEXT,

  brand_guess TEXT,
  model_guess TEXT,
  mpn_guess TEXT,

  specs_raw TEXT,

  http_status INTEGER,
  response_time_ms INTEGER
);
"""

DDL_SCRAPE_RUNS = """
CREATE TABLE IF NOT EXISTS scrape_runs (
  run_id TEXT PRIMARY KEY,
  site_name TEXT NOT NULL,
  category TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT NOT NULL,
  duration_s REAL NOT NULL,
  pages_requested INTEGER NOT NULL,
  listing_pages_ok INTEGER NOT NULL,
  detail_pages_ok INTEGER NOT NULL,
  products_parsed INTEGER NOT NULL,
  products_filtered INTEGER NOT NULL,
  products_upserted INTEGER NOT NULL,
  products_inserted INTEGER NOT NULL,
  products_updated INTEGER NOT NULL,
  errors INTEGER NOT NULL
);
"""

DDL_PRICE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS price_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,

  url TEXT NOT NULL,
  source TEXT NOT NULL,
  category TEXT NOT NULL,

  price TEXT,
  price_value REAL,
  currency TEXT,

  scraped_at TEXT NOT NULL,
  scrape_run_id TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_snapshots_url_run ON price_snapshots(url, scrape_run_id);

CREATE INDEX IF NOT EXISTS idx_snapshots_url ON price_snapshots(url);
CREATE INDEX IF NOT EXISTS idx_snapshots_scraped_at ON price_snapshots(scraped_at);
CREATE INDEX IF NOT EXISTS idx_snapshots_source_category ON price_snapshots(source, category);
CREATE INDEX IF NOT EXISTS idx_snapshots_url_scraped_at ON price_snapshots(url, scraped_at);
"""

DDL_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_products_source ON products(source);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_scraped_at ON products(scraped_at);
CREATE INDEX IF NOT EXISTS idx_products_source_category ON products(source, category);
CREATE INDEX IF NOT EXISTS idx_products_brand_model ON products(brand_guess, model_guess);
CREATE INDEX IF NOT EXISTS idx_products_posted_at ON products(posted_at);
"""

class SqliteStore:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._ensure_parent_dir()
        self._init_db()

    def _ensure_parent_dir(self) -> None:
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(DDL_PRODUCTS)
            conn.execute(DDL_SCRAPE_RUNS)
            conn.executescript(DDL_PRICE_SNAPSHOTS)

            rows = conn.execute("PRAGMA table_info(products);").fetchall()
            cols = { (r["name"] if isinstance(r, dict) or hasattr(r, "keys") else r[1]) for r in rows }
            if "condition" not in cols:
                conn.execute("ALTER TABLE products ADD COLUMN condition TEXT;")
            
            if "price_value" not in cols:
                conn.execute("ALTER TABLE products ADD COLUMN price_value REAL;")

            for stmt in [s.strip() for s in DDL_INDEXES.split(";") if s.strip()]:
                conn.execute(stmt)

            conn.commit()

    def upsert_products(self, products: Iterable[Product]) -> tuple[int, int, int]:
        """
        Returnează: (upserted_total, inserted, updated)

        Optimizare:
        - preluăm toate URL-urile existente din DB într-un singur SELECT (chunked),
        ca să evităm SELECT per produs.
        """
        products_list = list(products)
        if not products_list:
            return 0, 0, 0

        upserted = 0
        inserted = 0
        updated = 0

        urls = [str(p.url) for p in products_list]

        # SQLite are limită de variabile în query (de obicei 999).
        # Lăsăm o marjă de siguranță.
        CHUNK_SIZE = 800

        def chunks(lst: list[str], size: int):
            for i in range(0, len(lst), size):
                yield lst[i : i + size]

        with self._connect() as conn:
            cur = conn.cursor()

            # 1) Preluăm setul de URL-uri deja existente
            existing_urls: set[str] = set()
            for chunk in chunks(urls, CHUNK_SIZE):
                placeholders = ",".join(["?"] * len(chunk))
                cur.execute(
                    f"SELECT url FROM products WHERE url IN ({placeholders});",
                    chunk,
                )
                existing_urls.update(row[0] for row in cur.fetchall())

            last_snapshot_cache: dict[str, tuple[Optional[float], Optional[str]]] = {}

            # 2) UPSERT pentru fiecare produs + numărătoare insert/update
            for p in products_list:
                specs_raw_str = json.dumps(p.specs_raw, ensure_ascii=False) if p.specs_raw else None
                url_str = str(p.url)

                price_str = str(p.price) if p.price is not None else None
                price_val = float(p.price) if p.price is not None else None

                condition = None
                if p.specs_raw and isinstance(p.specs_raw, dict):
                    condition = p.specs_raw.get("stare")

                params = (
                    p.source,
                    p.category,
                    url_str,
                    p.scraped_at.isoformat(),
                    p.scrape_run_id,
                    p.title,
                    price_str,
                    price_val,
                    p.currency,
                    condition,
                    p.availability,
                    p.location,
                    p.posted_at.isoformat() if p.posted_at else None,
                    p.description_text,
                    p.description_html,
                    p.brand_guess,
                    p.model_guess,
                    p.mpn_guess,
                    specs_raw_str,
                    p.http_status,
                    p.response_time_ms,
                )

                cur.execute(
                    """
                    INSERT INTO products(
                        source, category, url, scraped_at, scrape_run_id,
                        title, price, price_value, currency, condition, availability, 
                        location, posted_at, description_text, description_html,
                        brand_guess, model_guess, mpn_guess, specs_raw,
                        http_status, response_time_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        scraped_at=excluded.scraped_at,
                        scrape_run_id=excluded.scrape_run_id,
                        title=excluded.title,
                        price=excluded.price,
                        price_value=excluded.price_value,
                        currency=excluded.currency,
                        condition=excluded.condition,
                        availability=excluded.availability,
                        location=excluded.location,
                        posted_at=excluded.posted_at,
                        description_text=excluded.description_text,
                        description_html=excluded.description_html,
                        brand_guess=excluded.brand_guess,
                        model_guess=excluded.model_guess,
                        mpn_guess=excluded.mpn_guess,
                        specs_raw=excluded.specs_raw,
                        http_status=excluded.http_status,
                        response_time_ms=excluded.response_time_ms
                    """,
                    params,
                )

                # snapshot only if we have a price (optional: store even null prices)
                if p.scrape_run_id and price_str is not None:
                    # 1) luăm ultimul snapshot pentru URL (din cache sau DB)
                    if url_str in last_snapshot_cache:
                        last_price_value, last_price_str = last_snapshot_cache[url_str]
                    else:
                        row = cur.execute(
                            """
                            SELECT price_value, price
                            FROM price_snapshots
                            WHERE url = ?
                            ORDER BY scraped_at DESC
                            LIMIT 1
                            """,
                            (url_str,),
                        ).fetchone()
                        if row:
                            last_price_value, last_price_str = row[0], row[1]
                        else:
                            last_price_value, last_price_str = None, None
                        last_snapshot_cache[url_str] = (last_price_value, last_price_str)

                    # 2) comparăm: dacă e identic, nu inserăm
                    same_value = (last_price_value is not None and price_val is not None and float(last_price_value) == float(price_val))
                    same_str = (last_price_str is not None and price_str is not None and str(last_price_str) == str(price_str))

                    if not (same_value or same_str):
                        cur.execute(
                            """
                            INSERT OR IGNORE INTO price_snapshots(
                                url, source, category, price, price_value, currency, scraped_at, scrape_run_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                url_str,
                                p.source,
                                p.category,
                                price_str,
                                price_val,
                                p.currency,
                                p.scraped_at.isoformat(),
                                p.scrape_run_id,
                            ),
                        )
                        # actualizăm cache-ul cu noul snapshot inserat
                        last_snapshot_cache[url_str] = (price_val, price_str)

                upserted += 1
                if url_str in existing_urls:
                    updated += 1
                else:
                    inserted += 1

            conn.commit()

        return upserted, inserted, updated
    
    def count_products(self) -> int:
        with self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM products;")
            return int(cur.fetchone()[0])
        
    def insert_scrape_run(self, stats) -> None:
        """
        Salvează un rezumat al unei rulări în tabela scrape_runs.
        stats este RunStats din pipeline.py
        """
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scrape_runs (
                run_id, site_name, category,
                started_at, finished_at, duration_s,
                pages_requested, listing_pages_ok, detail_pages_ok,
                products_parsed, products_filtered,
                products_upserted, products_inserted, products_updated,
                errors
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stats.scrape_run_id,
                    stats.site_name,
                    stats.category,
                    getattr(stats, "started_at", None) or "",   # completăm imediat mai jos în pipeline
                    getattr(stats, "finished_at", None) or "",
                    float(stats.duration_s),
                    int(stats.pages_requested),
                    int(stats.listing_pages_ok),
                    int(stats.detail_pages_ok),
                    int(stats.products_parsed),
                    int(stats.products_filtered),
                    int(stats.products_upserted),
                    int(stats.products_inserted),
                    int(stats.products_updated),
                    int(stats.errors),
                ),
            )

    def get_runs(self, limit: int = 50):
        with self._connect() as conn:
            cur = conn.execute(
                "SELECT * FROM scrape_runs ORDER BY finished_at DESC LIMIT ?",
                (limit,),
            )
            return [dict(row) for row in cur.fetchall()]