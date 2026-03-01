from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from app.models import Product


def write_products_csv(products: Iterable[Product], path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "source", "category", "url", "scraped_at", "scrape_run_id",
        "title", "price", "currency",
        "availability", "location", "posted_at",
        "brand_guess", "model_guess", "mpn_guess",
        "http_status", "response_time_ms",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for p in products:
            w.writerow({
                "source": p.source,
                "category": p.category,
                "url": p.url,
                "scraped_at": p.scraped_at.isoformat() if p.scraped_at else "",
                "scrape_run_id": p.scrape_run_id or "",
                "title": p.title,
                "price": str(p.price) if p.price is not None else "",
                "currency": p.currency,
                "availability": p.availability or "",
                "location": p.location or "",
                "posted_at": p.posted_at.isoformat() if p.posted_at else "",
                "brand_guess": p.brand_guess or "",
                "model_guess": p.model_guess or "",
                "mpn_guess": p.mpn_guess or "",
                "http_status": p.http_status if p.http_status is not None else "",
                "response_time_ms": p.response_time_ms if p.response_time_ms is not None else "",
            })