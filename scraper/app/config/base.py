from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class HttpConfig:
    timeout_s: int = 20
    max_retries: int = 3
    backoff_base_s: float = 1.0  # Timpul de bază pentru exponential backoff
    min_delay_s: float = 1.5    # Pauza minimă între request-uri
    max_delay_s: float = 3.5    # Pauza maximă pentru a părea "uman"

    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    )

# Instanțiem obiectul de configurare pentru a fi folosit în app
HTTP = HttpConfig()

BASE_DIR = Path(__file__).resolve().parents[2]
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "data_out" / "products.db")))

DB_PATH.parent.mkdir(parents=True, exist_ok=True)
(BASE_DIR / "logs").mkdir(parents=True, exist_ok=True)