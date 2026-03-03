from __future__ import annotations

import json
import sqlite3
from typing import Any, Dict
from datetime import timezone

from app.config.base import DB_PATH

from app.models import Product
from app.cleaning.normalize import (
    normalize_location,
    normalize_condition,
    effective_posted_at,
    normalize_title,
)

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS products_clean (
    url TEXT PRIMARY KEY,
    source TEXT,
    category TEXT,

    title_clean TEXT,
    brand_guess TEXT,
    model_guess TEXT,
    mpn_guess TEXT,

    price_ron REAL,
    currency TEXT,

    location_clean TEXT,
    county TEXT,
    city TEXT,

    condition_norm TEXT,
    posted_at_utc TEXT,
    scraped_at_utc TEXT,

    scrape_run_id TEXT
);
"""

def row_to_product(row: dict):
    # specs_raw vine din sqlite ca TEXT (JSON string) -> îl facem dict
    sr = row.get("specs_raw")
    if isinstance(sr, str):
        s = sr.strip()
        if not s or s.lower() in ("null", "none"):
            row["specs_raw"] = None
        else:
            try:
                row["specs_raw"] = json.loads(s)
            except Exception:
                # dacă e junk / string care nu e JSON valid
                row["specs_raw"] = None

    return Product(**row)


def main():
    if not DB_PATH.exists():
        raise SystemExit(f"DB not found: {DB_PATH}")

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    cur.execute(CREATE_SQL)

    # IMPORTANT:
    # presupun că ai tabelul "products" cu coloane care corespund modelului Product.
    # Dacă la tine se numește altfel (ex: product_snapshots), schimbă aici SELECT-ul.
    rows = cur.execute("SELECT * FROM products").fetchall()

    upserts = 0

    for r in rows:
        d = dict(r)
        p = row_to_product(d)

        loc_clean, county, city = normalize_location(p.location)
        cond = normalize_condition(
            p.condition,
            source=p.source,
            specs_raw=p.specs_raw if isinstance(p.specs_raw, dict) else None,
        )
        posted = effective_posted_at(p)

        title_clean = normalize_title(p.title)
        price_ron = p.price_value

        cur.execute(
            """
            INSERT INTO products_clean (
                url, source, category,
                title_clean, brand_guess, model_guess, mpn_guess,
                price_ron, currency,
                location_clean, county, city,
                condition_norm, posted_at_utc, scraped_at_utc,
                scrape_run_id
            ) VALUES (
                ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?
            )
            ON CONFLICT(url) DO UPDATE SET
                source=excluded.source,
                category=excluded.category,
                title_clean=excluded.title_clean,
                brand_guess=excluded.brand_guess,
                model_guess=excluded.model_guess,
                mpn_guess=excluded.mpn_guess,
                price_ron=excluded.price_ron,
                currency=excluded.currency,
                location_clean=excluded.location_clean,
                county=excluded.county,
                city=excluded.city,
                condition_norm=excluded.condition_norm,
                posted_at_utc=excluded.posted_at_utc,
                scraped_at_utc=excluded.scraped_at_utc,
                scrape_run_id=excluded.scrape_run_id
            """,
            (
                p.url, p.source, p.category,
                title_clean, p.brand_guess, p.model_guess, p.mpn_guess,
                price_ron, p.currency,
                loc_clean, county, city,
                cond,
                posted.isoformat(),
                p.scraped_at.astimezone(timezone.utc).isoformat(),
                p.scrape_run_id,
            ),
        )
        upserts += 1

    con.commit()
    con.close()

    print(f"products_clean upserted: {upserts}")


if __name__ == "__main__":
    main()