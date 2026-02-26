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
  currency TEXT,
  availability TEXT,
  location TEXT,
  posted_at TEXT,

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

DDL_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_products_source ON products(source);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category);
CREATE INDEX IF NOT EXISTS idx_products_scraped_at ON products(scraped_at);
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

            # 2) UPSERT pentru fiecare produs + numărătoare insert/update
            for p in products_list:
                specs_raw_str = json.dumps(p.specs_raw, ensure_ascii=False) if p.specs_raw else None
                url_str = str(p.url)

                params = (
                    p.source,
                    p.category,
                    url_str,
                    p.scraped_at.isoformat(),
                    p.scrape_run_id,
                    p.title,
                    str(p.price) if p.price is not None else None,
                    p.currency,
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
                        title, price, currency, availability, location, posted_at,
                        description_text, description_html,
                        brand_guess, model_guess, mpn_guess,
                        specs_raw,
                        http_status, response_time_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(url) DO UPDATE SET
                        scraped_at=excluded.scraped_at,
                        scrape_run_id=excluded.scrape_run_id,
                        title=excluded.title,
                        price=excluded.price,
                        currency=excluded.currency,
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