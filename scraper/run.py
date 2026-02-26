# scraper/run.py
from __future__ import annotations

import argparse
import sys # Adăugat pentru exit controlat

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
            except Exception:
                pass

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
        print(f"run_id:         {stats.scrape_run_id}")
        print(f"site:           {stats.site_name}")
        print(f"category:       {stats.category}")
        print(f"pages_ok:       {stats.listing_pages_ok}/{stats.pages_requested}")
        print(f"detail_ok:      {stats.detail_pages_ok}")
        print(f"parsed:         {stats.products_parsed}")
        print(f"upserted:       {stats.products_upserted}")
        print(f"inserted:       {stats.products_inserted}")
        print(f"updated:        {stats.products_updated}")
        print(f"errors:         {stats.errors}")
        print(f"duration_s:     {stats.duration_s}")
        print(f"db_total_rows:  {total}")

    except KeyboardInterrupt:
        print("\n[!] Scraper oprit manual de utilizator (Ctrl+C).")
        sys.exit(0)
    except Exception as e:
        print(f"\n[!] Eroare critică la rulare: {type(e).__name__}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()