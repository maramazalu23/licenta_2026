from pathlib import Path
import os
import warnings


BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"
ROOT_DIR = BASE_DIR.parent

# web/db pentru aplicatie
WEB_DB_PATH = BASE_DIR / "web.db"

# products.db din scraper - doar read-only
PRODUCTS_DB_PATH = ROOT_DIR / "scraper" / "data_out" / "products.db"


_secret = os.environ.get("SECRET_KEY")
if not _secret:
    warnings.warn("SECRET_KEY nu este setat. Se folosește cheia implicită de dezvoltare.")
    _secret = "dev-secret-key-change-me"


class Config:
    SECRET_KEY = _secret

    SQLALCHEMY_DATABASE_URI = f"sqlite:///{WEB_DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PRODUCTS_DB_PATH = PRODUCTS_DB_PATH
    DEBUG = True