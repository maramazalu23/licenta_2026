from __future__ import annotations
import os
from dataclasses import dataclass

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

# Căile pentru stocare
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, "data_out", "scraper.db")

# Ne asigurăm că folderul data_out există
os.makedirs(os.path.join(BASE_DIR, "data_out"), exist_ok=True)
os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)