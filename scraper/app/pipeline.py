from __future__ import annotations

import os
import uuid
import time # Adăugat pentru cronometrare
import logging
from pathlib import Path

from app.config.base import BASE_DIR
from dataclasses import dataclass
from typing import List, Optional
from app.models import Product
from app.storage.sqlite import SqliteStore
from app.sites.base import SiteScraper
from datetime import datetime, timezone
from app.storage.csv_writer import write_products_csv

logger = logging.getLogger("scraper.pipeline")

DEBUG_DIR = Path(BASE_DIR) / "data_out" / "debug"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)

@dataclass
class RunStats:
    scrape_run_id: str
    site_name: str
    category: str
    pages_requested: int
    started_at: str = ""
    finished_at: str = ""
    duration_s: float = 0.0 # Nou
    listing_pages_ok: int = 0
    detail_pages_ok: int = 0
    products_parsed: int = 0
    products_upserted: int = 0
    products_inserted: int = 0
    products_updated: int = 0
    errors: int = 0
    products_filtered: int = 0

def run_scrape(
    site: SiteScraper,
    site_name: str,
    category: str,
    max_pages: int,
    max_products: Optional[int] = None,
) -> tuple[List[Product], RunStats]:
    run_id = str(uuid.uuid4())
    start_time = time.time()
    
    stats = RunStats(
        scrape_run_id=run_id,
        site_name=site_name,
        category=category,
        pages_requested=max_pages,
    )

    stats.started_at = datetime.now(timezone.utc).isoformat()

    products: List[Product] = []
    listing_urls = list(site.iter_listing_urls(category=category, max_pages=max_pages))

    logger.info("--- Starting Scrape Run [%s] for %s ---", run_id, site_name)

    for li, listing_url in enumerate(listing_urls, start=1):
        try:
            site.http.polite_sleep()
            listing_res = site.http.get(listing_url)

            if listing_res.status_code != 200:
                stats.errors += 1
                logger.warning("[%s] Listing page FAIL %s: %s", site_name, listing_res.status_code, listing_url)
                continue

            stats.listing_pages_ok += 1
            detail_urls = site.parse_listing_page(listing_res.text)

            if not detail_urls:
                debug_path = DEBUG_DIR / f"{site_name}_listing_empty_{run_id}_p{li}.html"
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(listing_res.text)

                logger.info("[debug] Saved empty listing HTML to: %s", debug_path)

            logger.info("[%s] Page %s/%s: Found %s items", site_name, li, len(listing_urls), len(detail_urls))

            for durl in detail_urls:
                if max_products is not None and len(products) >= max_products:
                    stats.duration_s = round(time.time() - start_time, 2)
                    stats.finished_at = datetime.now(timezone.utc).isoformat()
                    return products, stats

                try:
                    site.http.polite_sleep()
                    detail_res = site.http.get(durl)

                    if detail_res.status_code != 200:
                        stats.errors += 1
                        continue

                    stats.detail_pages_ok += 1
                    
                    # Aici se produce magia: Parser + Pydantic Validation
                    p = site.parse_detail_page(detail_res.text, url=durl, category=category)

                    # Filtrare site-specific (implementată în scraper; default True)
                    try:
                        keep = site.filter_product(p)
                    except Exception as e:
                        stats.errors += 1
                        logger.warning("Filter error for %s: %s: %s", p.url, type(e).__name__, e)
                        keep = False

                    if not keep:
                        # IMPORTANT: trebuie să existe în RunStats (dacă nu, îl adăugăm la pasul următor)
                        stats.products_filtered += 1
                        continue

                    p.source = site_name
                    p.http_status = detail_res.status_code
                    p.response_time_ms = detail_res.elapsed_ms
                    p.scrape_run_id = run_id

                    products.append(p)
                    stats.products_parsed += 1

                    if stats.products_parsed % 5 == 0:
                        logger.info("   > Parsed %s products...", stats.products_parsed)

                except Exception as e:
                    stats.errors += 1
                    logger.warning("   ! Error parsing %s: %s: %s", durl, type(e).__name__, e)

        except Exception as e:
            stats.errors += 1
            logger.exception("!!! Critical Listing Error: %s: %s", type(e).__name__, e)
        
    stats.duration_s = round(time.time() - start_time, 2)
    stats.finished_at = datetime.now(timezone.utc).isoformat()
    return products, stats

def run_and_store(
    site_scraper: SiteScraper,
    site_name: str,
    category: str,
    max_pages: int,
    max_products: Optional[int] = None,
    db_path: Optional[str] = None,
) -> RunStats:
    products, stats = run_scrape(
        site=site_scraper,
        site_name=site_name,
        category=category,
        max_pages=max_pages,
        max_products=max_products,
    )

    if products:
        store = SqliteStore(db_path=db_path) if db_path else SqliteStore()
        upserted, inserted, updated = store.upsert_products(products)
        stats.products_upserted = upserted
        stats.products_inserted = inserted
        stats.products_updated = updated

        store.insert_scrape_run(stats)
        logger.info("[db] Saved run summary to scrape_runs: %s", stats.scrape_run_id)

        logger.info(
            "--- Finished: Upserted %s/%s (inserted=%s, updated=%s) in %ss ---",
            upserted, len(products), inserted, updated, stats.duration_s
        )

        export_path = Path(BASE_DIR) / "data_out" / "exports" / f"{site_name}_{stats.scrape_run_id}.csv"
        write_products_csv(products, export_path)
        logger.info("[export] Wrote CSV: %s", export_path)
    else:
        logger.warning("--- Finished: No products were found/parsed. ---")
        store = SqliteStore(db_path=db_path) if db_path else SqliteStore()
        store.insert_scrape_run(stats)
        logger.info("[db] Saved run summary to scrape_runs: %s", stats.scrape_run_id)        
    return stats