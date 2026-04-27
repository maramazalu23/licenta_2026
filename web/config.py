from pathlib import Path
import os


BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"
ROOT_DIR = BASE_DIR.parent

# web/db pentru aplicație
WEB_DB_PATH = BASE_DIR / "web.db"

# products.db din scraper - doar read-only
PRODUCTS_DB_PATH = ROOT_DIR / "scraper" / "data_out" / "products.db"


class Config:
    DEBUG = os.environ.get("FLASK_DEBUG", "0") == "1"

    SECRET_KEY = os.environ.get("SECRET_KEY", "licenta-dev-secret-key")

    SQLALCHEMY_DATABASE_URI = f"sqlite:///{WEB_DB_PATH}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    PRODUCTS_DB_PATH = PRODUCTS_DB_PATH

    UPLOAD_FOLDER = APP_DIR / "static" / "uploads" / "listings"
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024