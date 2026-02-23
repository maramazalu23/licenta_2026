from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, Literal, Dict, Any
import re

from pydantic import BaseModel, Field, field_validator, ConfigDict

SourceType = Literal["publi24", "pcgarage", "cel", "okazii"]
CurrencyType = Literal["RON"]  # păstrăm simplu în MVP


class Product(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    # --- Identitate și Meta ---
    source: SourceType
    category: str
    url: str  # mai permisiv decât HttpUrl (mai safe pt scraping)
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
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
    def parse_price(cls, v: Any) -> Optional[Decimal]:
        if v is None:
            return None

        if isinstance(v, (int, float, Decimal)):
            try:
                return Decimal(str(v))
            except (InvalidOperation, ValueError):
                return None

        s = str(v).strip().lower()

        if any(word in s for word in ["contact", "negociabil", "la cerere", "n/a", "schimb"]):
            return None

        clean_s = re.sub(r"[^0-9,.]", "", s)
        if not clean_s:
            return None

        # 1.234,56 -> 1234.56
        if "," in clean_s and "." in clean_s:
            clean_s = clean_s.replace(".", "").replace(",", ".")
        elif "," in clean_s:
            clean_s = clean_s.replace(",", ".")
        elif "." in clean_s:
            if clean_s.count(".") > 1:
                clean_s = clean_s.replace(".", "")
            else:
                parts = clean_s.split(".")
                if len(parts[-1]) == 3:
                    clean_s = clean_s.replace(".", "")

        try:
            return Decimal(clean_s)
        except (InvalidOperation, ValueError):
            return None