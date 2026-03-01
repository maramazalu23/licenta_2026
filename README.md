# Platformă de estimare a valorii reale pentru laptopuri (licență) – Data Collection Scraper

Acest proiect face parte din lucrarea mea de licență și implementează un pipeline de colectare și curățare date pentru laptopuri din surse online (România).
Scopul este construirea unei baze de date cu prețuri și atribute (new/second-hand, brand, MPN, etc.) pentru analiză și estimarea “valorii reale” din piață.

## Arhitectură (overview)
run.py (CLI)
|
v
pipeline.py -> http.py (requests + Playwright fallback)
|
v
sites/ (publi24, pcgarage)
|
v
models.py (Pydantic validation + normalize_price)
|
v
sqlite.py (UPSERT products + scrape_runs) + exports/*.csv

## Structura proiectului

- `scraper/run.py` – CLI pentru rulare pe site/categorie
- `scraper/app/pipeline.py` – orchestrare: listing -> detail -> parse -> filter -> store
- `scraper/app/core/http.py` – client HTTP (requests) + fallback JS (Playwright)
- `scraper/app/sites/` – scrapers per site (`publi24.py`, `pcgarage.py`)
- `scraper/app/models.py` – schema `Product` (Pydantic), normalizări (ex: preț)
- `scraper/app/storage/sqlite.py` – stocare SQLite, UPSERT, `scrape_runs`
- `scraper/app/storage/csv_writer.py` – export CSV per run
- `scraper/data_out/` – baza de date + exporturi + debug HTML

## Instalare

În PowerShell, din root-ul repo-ului:

```powershell
.\.venv\Scripts\Activate.ps1
cd .\scraper\
pip install -r requirements.txt
python -m playwright install chromium