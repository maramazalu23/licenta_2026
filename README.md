# Licenta 2026 — IT Products Market Scraper & Price Analysis

## Overview

This project is part of a Bachelor's thesis focused on **collecting, cleaning, and analyzing real-world market data for IT products** (currently laptops).

The system automatically scrapes listings from Romanian marketplaces and online stores, stores structured data in a database, and prepares datasets for price analysis.

Currently implemented sources:

* **Publi24** (second-hand marketplace)
* **PCGarage** (new product retailer)

The project includes:

* modular scrapers
* automatic filtering of invalid listings
* structured product storage
* price snapshot tracking
* dataset export for analysis

---

# Project Architecture

```
licenta_2026/
│
├── scraper/
│   │
│   ├── app/
│   │   ├── cleaning/          # data normalization scripts
│   │   ├── config/            # site policies & base configuration
│   │   ├── core/              # HTTP client, logging, utilities
│   │   ├── sites/             # site-specific scrapers
│   │   ├── storage/           # database and CSV exporters
│   │   ├── filters.py         # marketplace filtering logic
│   │   ├── models.py          # Product Pydantic model
│   │   └── pipeline.py        # scraping pipeline
│   │
│   ├── data_out/              # generated runtime data
│   │   ├── exports/           # exported datasets
│   │   ├── filtered/          # rejected listings (with reasons)
│   │   ├── debug/             # HTML debug dumps
│   │   ├── browser_profile/   # Playwright browser profile
│   │   ├── browser_state/     # Playwright browser state
│   │   └── products.db        # SQLite database
│   │
│   ├── logs/                  # scraper logs
│   ├── scripts/               # analysis / dataset scripts
│   ├── tests/                 # DB and data validation checks
│   │
│   ├── check_coverage_sql.py
│   ├── check_db.py
│   ├── vacuum_db.py
│   ├── requirements.txt
│   └── run.py                 # main entry point
│
└── README.md
```

---

# Data Pipeline

The scraper pipeline performs the following steps:

1. **Fetch listing pages**
2. **Extract product URLs**
3. **Fetch product detail pages**
4. **Parse product information**
5. **Validate using Pydantic models**
6. **Filter invalid listings**
7. **Store results in SQLite**
8. **Create CSV dataset exports**

Pipeline execution statistics are saved in the database.

---

# Data Model

Each scraped product contains:

| Field            | Description              |
| ---------------- | ------------------------ |
| source           | Website source           |
| url              | Product URL              |
| title            | Listing title            |
| price            | Product price            |
| currency         | Currency (RON)           |
| location         | Seller location          |
| posted_at        | Listing date             |
| condition        | Product condition        |
| description_text | Clean description        |
| brand_guess      | Detected brand           |
| model_guess      | Detected model           |
| mpn_guess        | Manufacturer part number |
| specs_raw        | Raw specifications       |

---

# Filtering System

Marketplace listings often contain invalid products such as:

* accessories
* spare parts
* defective devices
* repair services

The filtering system uses a **scoring-based heuristic model** that evaluates:

* laptop keywords
* brand presence
* CPU / RAM / storage signals
* screen size
* banned keywords

Rejected listings are exported with reasons:

```
data_out/filtered/publi24_<run_id>_filtered.csv
```

Example rejection reasons:

```
defect_ban:defect
title_hard_ban_strict:mouse
reject_component_only
```

---

# HTTP Scraper Engine

The scraper includes a custom HTTP client with:

* rotating User-Agent headers
* retry with exponential backoff
* automatic block detection
* Playwright fallback for JS-protected sites
* domain-specific scraping policies

Example policies:

```
app/config/sites.py
```

---

# Running the Scraper

From the project root:

```
python scraper/run.py publi24 --pages 2 --max-products 50
```

Example commands:

### Scrape Publi24

```
python scraper/run.py publi24 --pages 2 --max-products 50
```

### Scrape PCGarage

```
python scraper/run.py pcgarage --pages 1 --max-products 20
```

Optional arguments:

```
--pages           number of listing pages
--max-products    safety limit
--log-level       DEBUG / INFO / WARNING
--db              custom database path
```

---

# Output Data

### SQLite database

```
scraper/data_out/products.db
```

Tables:

```
products
price_snapshots
scrape_runs
```

---

### Dataset exports

```
scraper/data_out/exports/
```

Example:

```
publi24_<run_id>.csv
pcgarage_<run_id>.csv
```

---

# Data Quality Checks

Utility scripts are included for verifying the dataset:

```
python scraper/check_db.py
```

Checks include:

* product counts
* missing fields
* duplicate URLs
* snapshot coverage

---

# Technologies Used

* Python
* Requests
* Playwright
* BeautifulSoup
* Pydantic
* SQLite

---

# Future Improvements

Planned extensions:

* additional marketplaces (OLX, CEL.ro)
* price normalization
* machine learning price estimation
* product matching across marketplaces
* automated data cleaning pipeline

---

# Author

Bachelor Thesis Project
Faculty of Economic Cybernetics, Statistics and Informatics
2026
