from __future__ import annotations

import uuid
import time # Adăugat pentru cronometrare
from dataclasses import dataclass
from typing import List, Optional

from app.models import Product
from app.storage.sqlite import SqliteStore
from app.sites.base import SiteScraper

@dataclass
class RunStats:
    scrape_run_id: str
    site_name: str
    category: str
    pages_requested: int
    duration_s: float = 0.0 # Nou
    listing_pages_ok: int = 0
    detail_pages_ok: int = 0
    products_parsed: int = 0
    products_saved: int = 0
    errors: int = 0

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

    products: List[Product] = []
    listing_urls = list(site.iter_listing_urls(category=category, max_pages=max_pages))

    print(f"--- Starting Scrape Run [{run_id}] for {site_name} ---")

    for li, listing_url in enumerate(listing_urls, start=1):
        try:
            site.http.polite_sleep()
            listing_res = site.http.get(listing_url)

            if listing_res.status_code != 200:
                stats.errors += 1
                print(f"[{site_name}] Listing page FAIL {listing_res.status_code}: {listing_url}")
                continue

            stats.listing_pages_ok += 1
            detail_urls = site.parse_listing_page(listing_res.text)

            if not detail_urls:
                continue

            print(f"[{site_name}] Page {li}/{len(listing_urls)}: Found {len(detail_urls)} items")

            for durl in detail_urls:
                if max_products is not None and len(products) >= max_products:
                    stats.duration_s = round(time.time() - start_time, 2)
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

                    # Filtru MVP pentru Publi24: eliminăm accesorii din categoria "laptopuri"
                    if site_name == "publi24" and category == "laptopuri":
                        t = (p.title or "").lower()
                        banned = [
                            # accesorii
                            "baterie", "incarcator", "alimentator", "display", "ecran",
                            "husa", "cooler", "stand", "tastatura", "mouse",
                            "cablu", "ram", "ssd", "hard disk", "hdd", "placa video",
                            "placa baza", "motherboard", "carcasa", "piese",

                            # alte dispozitive
                            "tableta", "tablet", "ipad", "chromebook",
                            "telefon", "smartphone", "monitor",
                            "mini pc", "desktop", "unitate centrala"
                        ]

                        # dacă conține banned → skip
                        if any(b in t for b in banned):
                            continue

                        # trebuie să conțină măcar unul din indicatorii de laptop real
                        allowed_indicators = [
                            "laptop", "notebook", "ultrabook",
                            "macbook", "thinkpad", "vivobook",
                            "ideapad", "latitude", "probook",
                            "rog", "aspire", "yoga"
                        ]

                        if not any(a in t for a in allowed_indicators):
                            continue

                    p.source = site_name
                    p.http_status = detail_res.status_code
                    p.response_time_ms = detail_res.elapsed_ms
                    p.scrape_run_id = run_id

                    products.append(p)
                    stats.products_parsed += 1

                    if stats.products_parsed % 5 == 0:
                        print(f"   > Parsed {stats.products_parsed} products...")

                except Exception as e:
                    stats.errors += 1
                    print(f"   ! Error parsing {durl}: {type(e).__name__}: {e}")

        except Exception as e:
            stats.errors += 1
            print(f"!!! Critical Listing Error: {type(e).__name__}: {e}")

    stats.duration_s = round(time.time() - start_time, 2)
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
        saved = store.upsert_products(products)
        stats.products_saved = saved
        print(f"--- Finished: Saved {saved}/{len(products)} products in {stats.duration_s}s ---")
    else:
        print("--- Finished: No products were found/parsed. ---")
        
    return stats