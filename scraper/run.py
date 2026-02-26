# scraper/run.py
from __future__ import annotations

import argparse
import sys # Adăugat pentru exit controlat
import os
import logging

from app.core.logging import setup_logging
from app.config.base import BASE_DIR
from app.core.http import HttpClient
from app.pipeline import run_and_store
from app.storage.sqlite import SqliteStore
from app.sites.publi24 import Publi24Scraper
from app.sites.pcgarage import PcGarageScraper

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Licenta 2026 - Market scraper")
    parser.add_argument("site", choices=["publi24", "pcgarage"], help="Source website to scrape")
    parser.add_argument("--category", default="laptopuri", help="Internal category name")
    parser.add_argument("--pages", type=int, default=1, help="Number of listing pages")
    parser.add_argument("--max-products", type=int, default=None, help="Safety limit")
    parser.add_argument("--db", default=None, help="Custom SQLite path")
    return parser

def main():
    parser = build_parser()
    args = parser.parse_args()
    # Logging (salvează în scraper/logs/scraper.log)
    log_dir = os.path.join(BASE_DIR, "logs")
    setup_logging(log_dir=log_dir)
    logger = logging.getLogger("scraper")
    if args.pages < 1:
        raise ValueError("--pages must be >= 1")
    if args.max_products is not None and args.max_products < 1:
        raise ValueError("--max-products must be >= 1")

    http = HttpClient()

    try:
        if args.site == "publi24":
            scraper = Publi24Scraper(http)
            stats = run_and_store(
                site_scraper=scraper,
                site_name="publi24",
                category=args.category,
                max_pages=args.pages,
                max_products=args.max_products,
                db_path=args.db,
            )
        elif args.site == "pcgarage":
            # WARM-UP REQUEST (important pentru 403)
            try:
                http.get("https://www.pcgarage.ro/")
            except Exception as e:
                logger.warning("Warm-up PCGarage eșuat: %s: %s", type(e).__name__, e)

            scraper = PcGarageScraper(http)

            stats = run_and_store(
                site_scraper=scraper,
                site_name="pcgarage",
                category=args.category,
                max_pages=args.pages,
                max_products=args.max_products,
                db_path=args.db,
            )
        else:
            raise ValueError(f"Unsupported site: {args.site}")

        # Rezumat final + verificare DB
        store = SqliteStore(db_path=args.db) if args.db else SqliteStore()
        total = store.count_products()
        
        print("\n=== RUN SUMMARY ===")
        logger.info("=== RUN SUMMARY ===")
        logger.info("run_id:         %s", stats.scrape_run_id)
        logger.info("site:           %s", stats.site_name)
        logger.info("category:       %s", stats.category)
        logger.info("pages_ok:       %s/%s", stats.listing_pages_ok, stats.pages_requested)
        logger.info("detail_ok:      %s", stats.detail_pages_ok)
        logger.info("parsed:         %s", stats.products_parsed)
        logger.info("filtered:       %s", getattr(stats, "products_filtered", 0))
        logger.info("upserted:       %s", stats.products_upserted)
        logger.info("inserted:       %s", stats.products_inserted)
        logger.info("updated:        %s", stats.products_updated)
        logger.info("errors:         %s", stats.errors)
        logger.info("duration_s:     %s", stats.duration_s)
        logger.info("db_total_rows:  %s", total)

    except KeyboardInterrupt:
        logger.warning("Scraper oprit manual de utilizator (Ctrl+C).")
        sys.exit(0)
    except Exception as e:
        logger.exception("Eroare critică la rulare: %s: %s", type(e).__name__, e)
        sys.exit(1)

if __name__ == "__main__":
    main()