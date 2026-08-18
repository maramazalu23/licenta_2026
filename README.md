# IT Resell — Laptop Market Analysis and Evaluation System

This project was developed as part of the bachelor's thesis and proposes a web application for analyzing the market of new and second-hand laptops. The system collects data from online sources, normalizes the relevant information, and uses it to estimate a recommended price, evaluate the attractiveness of a listing, and support decision-making for buyers and sellers.

The project consists of two main components:

- `scraper/` — the data collection, cleaning, and preparation component;
- `web/` — the Flask application for users, evaluations, listings, favorites, notifications, and the administrative dashboard.

---

## 1. Project structure

```text
licenta_2026/
│
├── scraper/
│   ├── run.py
│   ├── daily_scrape.ps1
│   ├── requirements.txt
│   ├── app/
│   │   ├── core/
│   │   │   └── http.py
│   │   ├── sites/
│   │   │   ├── publi24.py
│   │   │   └── pcgarage.py
│   │   ├── storage/
│   │   │   └── sqlite.py
│   │   └── models.py
│   │
│   ├── scripts/
│   │   ├── build_clean_table.py
│   │   ├── normalize_clean.py
│   │   ├── build_analysis_view.py
│   │   ├── build_analysis_dataset.py
│   │   └── checks/
│   │       └── check_analysis_view.py
│   │
│   └── data_out/
│       └── products.db
│
├── web/
│   ├── run.py
│   ├── web.db
│   ├── requirements.txt
│   ├── app/
│   │   ├── __init__.py
│   │   ├── models.py
│   │   ├── routes.py
│   │   ├── services.py
│   │   ├── db_market.py
│   │   │
│   │   ├── scoring/
│   │   │   ├── price_engine.py
│   │   │   ├── depreciation.py
│   │   │   └── attractiveness.py
│   │   │
│   │   ├── templates/
│   │   │   ├── base.html
│   │   │   ├── index.html
│   │   │   ├── evaluate.html
│   │   │   ├── listings.html
│   │   │   ├── profile.html
│   │   │   ├── favorites.html
│   │   │   ├── notifications.html
│   │   │   ├── admin_dashboard.html
│   │   │   ├── admin_analytics.html
│   │   │   └── admin_history.html
│   │   │
│   │   └── static/
│   │       ├── css/
│   │       │   └── main.css
│   │       └── uploads/
│   │           └── listings/
│   │
│   └── config.py
│
└── README.md
```

---

## 2. Technologies used

- Python 3
- Flask, SQLAlchemy, Flask-Login, Flask-WTF
- SQLite
- BeautifulSoup, Playwright
- Chart.js, Bootstrap 5
- PowerShell + Windows Task Scheduler for automation

---

## 3. Scraping component

The `scraper/` component collects laptop data from two sources:

- **Publi24** — second-hand products;
- **PCGarage** — new products.

The data is stored in:

```text
scraper/data_out/products.db
```

Main tables:

| Table / View | Content |
|---|---|
| `products` | Raw collected products |
| `scrape_runs` | Run history |
| `price_snapshots` | Price snapshots |
| `products_clean` | Cleaned and normalized products |
| `products_analysis` | Final view used by the web application |

---

## 4. Running the scraper

```powershell
cd C:\Users\User\licenta_2026\scraper
..\.venv\Scripts\activate
```

**Publi24:**
```powershell
python run.py publi24 --category laptopuri --pages 2 --max-products 20
```

**PCGarage:**
```powershell
python run.py pcgarage --category laptopuri --pages 1 --max-products 20
```

**Rebuild dataset after collection:**
```powershell
python -m scripts.build_analysis_dataset
```

**Database compaction:**
```powershell
python -m scripts.vacuum_db
```

---

## 5. Scraper automation

The project includes a PowerShell script for automatically updating the data:

```text
scraper/daily_scrape.ps1
```

The script runs the commands required to update the data: collecting products from the configured sources, rebuilding the analysis dataset, and compacting the database.

**Manual run:**
```powershell
cd C:\Users\User\licenta_2026\scraper
powershell -ExecutionPolicy Bypass -File .\daily_scrape.ps1
```

**Automatic daily scheduling at 12:00:**

The script can be scheduled through Windows Task Scheduler to run daily at 12:00. Configuration steps:

1. Open **Task Scheduler** → *Create Basic Task*
2. Set the trigger: **Daily**, at **12:00**
3. Set the action: **Start a program**
   - Program: `powershell.exe`
   - Arguments: `-ExecutionPolicy Bypass -File "C:\Users\User\licenta_2026\scraper\daily_scrape.ps1"`
   - Start in: `C:\Users\User\licenta_2026\scraper`
4. Save the task

This approach allows the data to be updated periodically without integrating a scheduler directly into the Flask application.

---

## 6. Web component

The Flask application uses two databases:

| Database | Role |
|---|---|
| `scraper/data_out/products.db` | Market data, read-only access |
| `web/web.db` | Application data (users, evaluations, listings, favorites, notifications) |

---

## 7. Application roles

### Admin
- Administrative dashboard with metrics and charts
- Global evaluation history with filters
- Access to all published listings

### Seller
- Evaluates products and publishes listings
- Uploads images for listings
- Receives notifications about buyer interest
- Manages their own listings

### Buyer
- Explores products from the market database
- Adds listings to favorites
- Receives personalized suggestions based on favorites

---

## 8. Main functionalities

### Product evaluation

The user completes a form with title, description, brand, RAM, condition, asking price, and, optionally, the model family. The application estimates:

- the recommended price (based on the median of the market segment);
- the price score, which indicates the positioning of the asking price relative to the market segment;
- the depreciation score (relative to the median price of new products);
- the listing attractiveness score, which evaluates how complete and clear the listing is.
- similar products from the database.

### Publishing a listing

A seller can publish a listing starting from a saved evaluation and can upload an image of the product. Images are stored in:

```text
web/app/static/uploads/listings/
```

When a listing is deleted, the associated image is also automatically deleted from disk.

### Favorites and recommendations

Buyers can save listings to favorites. The application generates personalized suggestions based on preferred market segments (brand + model_family + ram_gb).

### Seller notifications

Sellers receive notifications when buyers add to favorites listings from the same segment as their products. The notification also includes the estimated median market price for the respective segment.

---

## 9. Running the web application

```powershell
cd C:\Users\User\licenta_2026\web
..\.venv\Scripts\activate
python -m flask --app run.py run
```

The application starts at: `http://127.0.0.1:5000`

Note: the interface uses Bootstrap and Chart.js via CDN. For fully offline operation, these libraries would need to be downloaded locally and served from the Flask application's static folder.

---

## 10. Configuration

Configuration file: `web/config.py`

| Parameter | Default value |
|---|---|
| `SECRET_KEY` | `licenta-dev-secret-key` (development) |
| `UPLOAD_FOLDER` | `web/app/static/uploads/listings/` |
| `MAX_CONTENT_LENGTH` | 5 MB |

For production, set the `SECRET_KEY` environment variable.

---

## 11. Creating an admin account

```powershell
cd C:\Users\User\licenta_2026\web
..\.venv\Scripts\activate
python -c "from app import create_app; from app.services import set_user_role; app=create_app(); app.app_context().push(); print(set_user_role('email@example.com','admin'))"
```

Replace `email@example.com` with the address of the account that needs to be promoted.

---

## 12. Database notes

The application automatically creates missing tables in `web.db` through `db.create_all()`. If new columns are added to the models after the database has been created, a manual migration is required.

**Example — add the `image_filename` column if it is missing:**

```powershell
python -c "import sqlite3; con=sqlite3.connect('web.db'); cur=con.cursor(); cols=[r[1] for r in cur.execute('PRAGMA table_info(listings)')]; cur.execute('ALTER TABLE listings ADD COLUMN image_filename TEXT') if 'image_filename' not in cols else None; con.commit(); con.close(); print('OK')"
```

---

## 13. Testing

```powershell
cd C:\Users\User\licenta_2026\scraper
..\.venv\Scripts\activate
pytest -q
```

---

## 14. Files excluded from the repository

```text
__pycache__/
.pytest_cache/
*.pyc
*.db-shm
*.db-wal
scraper/logs/
scraper/data_out/browser_profile/
web/app/static/uploads/listings/
```

`products.db` can be kept to allow the application to run without restarting the scraping process from scratch. Optionally, `web.db` can be kept if the inclusion of demonstration users and listings is desired.

---

## 15. Project purpose

The purpose of the project is to develop an integrated system for collecting, analyzing, and using market data in the process of evaluating new and second-hand laptops.

It can be used for:

- estimating an indicative price based on real market data;
- comparing with similar products;
- analyzing the difference between the asking price and the market value;
- personalizing the experience for buyers;
- informing sellers about existing interest on the platform;
- monitoring activity through the administrative dashboard.
