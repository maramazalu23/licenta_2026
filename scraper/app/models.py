from __future__ import annotations

import re

from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional, Literal, Dict, Any

from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime, timezone

SourceType = Literal["publi24", "pcgarage", "cel", "okazii"]
CurrencyType = Literal["RON"]  # păstrăm simplu în MVP


class Product(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # --- Identitate și Meta ---
    source: SourceType
    category: str
    url: str  # mai permisiv decât HttpUrl (mai safe pt scraping)
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scrape_run_id: Optional[str] = None

    # --- Conținut Principal ---
    title: str
    price: Optional[Decimal] = None
    currency: CurrencyType = "RON"

    # --- Detalii Specifice ---
    availability: Optional[str] = None
    location: Optional[str] = None
    posted_at: Optional[datetime] = None

    description_text: Optional[str] = None
    description_html: Optional[str] = None

    # --- Atribute pentru Matching (Iterația 2) ---
    brand_guess: Optional[str] = None
    model_guess: Optional[str] = None
    mpn_guess: Optional[str] = None

    # --- Date Brute / Tehnice ---
    specs_raw: Optional[Dict[str, Any]] = None
    http_status: Optional[int] = None
    response_time_ms: Optional[int] = None

    @field_validator("title")
    @classmethod
    def clean_title(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Titlul nu poate fi gol")
        return " ".join(v.split()).strip()

    @field_validator("price", mode="before")
    @classmethod
    def normalize_price(cls, v: Any) -> Optional[Decimal]:
        if v is None:
            return None

        s = str(v).strip()
        if not s:
            return None

        # scoate currency words
        s = re.sub(r"\b(lei|ron)\b", "", s, flags=re.I).strip()

        # elimină spații (și NBSP)
        s = s.replace("\u00a0", "").replace(" ", "")

        # dacă avem și virgulă, presupunem că virgula e zecimală
        # ex: 6.398,99 -> 6398.99
        if "," in s:
            s = s.replace(".", "").replace(",", ".")
        # altfel: 6398.990015 rămâne ok

        try:
            d = Decimal(s)
        except InvalidOperation:
            return None

        d = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return d