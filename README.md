# IT Resell — Sistem de analiză și evaluare a pieței laptopurilor

Acest proiect a fost realizat în cadrul lucrării de licență și propune o aplicație web pentru analiza pieței laptopurilor noi și second-hand. Sistemul colectează date din surse online, normalizează informațiile relevante și le utilizează pentru estimarea unui preț recomandat, evaluarea atractivității unui anunț și susținerea deciziilor pentru cumpărători și vânzători.

Proiectul este format din două componente principale:

- `scraper/` — componenta de colectare, curățare și pregătire a datelor;
- `web/` — aplicația Flask pentru utilizatori, evaluări, anunțuri, favorite, notificări și dashboard administrativ.

---

## 1. Structura proiectului

```text
licenta_2026/
│
├── scraper/
│   ├── app/
│   │   ├── scrapers/
│   │   ├── cleaning/
│   │   ├── pipeline/
│   │   └── filters.py
│   ├── scripts/
│   │   ├── build_clean_table.py
│   │   ├── normalize_clean.py
│   │   ├── build_analysis_view.py
│   │   ├── build_analysis_dataset.py
│   │   └── vacuum_db.py
│   ├── data_out/
│   │   └── products.db
│   ├── run.py
│   └── daily_scrape.ps1
│
├── web/
│   ├── app/
│   │   ├── templates/
│   │   ├── static/
│   │   ├── models.py
│   │   ├── routes.py
│   │   ├── services.py
│   │   ├── db_market.py
│   │   └── scoring/
│   ├── config.py
│   ├── run.py
│   └── web.db
│
├── requirements.txt
└── README.md
```

---

## 2. Tehnologii utilizate

- Python 3
- Flask, SQLAlchemy, Flask-Login, Flask-WTF
- SQLite
- BeautifulSoup, Playwright
- Chart.js, Bootstrap 5
- PowerShell + Windows Task Scheduler pentru automatizare

---

## 3. Componenta de scraping

Componenta `scraper/` colectează date despre laptopuri din două surse:

- **Publi24** — produse second-hand;
- **PCGarage** — produse noi.

Datele sunt salvate în:

```text
scraper/data_out/products.db
```

Tabele principale:

| Tabel / View | Conținut |
|---|---|
| `products` | Produse brute colectate |
| `scrape_runs` | Istoricul rulărilor |
| `price_snapshots` | Snapshot-uri de preț |
| `products_clean` | Produse curățate și normalizate |
| `products_analysis` | View final folosit de aplicația web |

---

## 4. Rularea scraperului

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

**Reconstruire dataset după colectare:**
```powershell
python -m scripts.build_analysis_dataset
```

**Compactare bază de date:**
```powershell
python -m scripts.vacuum_db
```

---

## 5. Automatizarea scraperului

Proiectul include un script PowerShell pentru actualizarea automată a datelor:

```text
scraper/daily_scrape.ps1
```

Scriptul rulează automat în ordine:

1. Scraperul pentru Publi24
2. Scraperul pentru PCGarage
3. Reconstruirea tabelei curățate
4. Reconstruirea view-ului de analiză
5. Compactarea bazei de date

**Rulare manuală:**
```powershell
cd C:\Users\User\licenta_2026\scraper
powershell -ExecutionPolicy Bypass -File .\daily_scrape.ps1
```

**Programare automată zilnică la ora 12:00:**

Scriptul poate fi programat prin Windows Task Scheduler să ruleze zilnic la ora 12:00. Pașii de configurare:

1. Deschide **Task Scheduler** → *Create Basic Task*
2. Setează trigger: **Daily**, ora **12:00**
3. Setează acțiunea: **Start a program**
   - Program: `powershell.exe`
   - Argumente: `-ExecutionPolicy Bypass -File "C:\Users\User\licenta_2026\scraper\daily_scrape.ps1"`
   - Start in: `C:\Users\User\licenta_2026\scraper`
4. Salvează task-ul

Această abordare permite actualizarea periodică a datelor fără a integra un scheduler direct în aplicația Flask.

---

## 6. Componenta web

Aplicația Flask folosește două baze de date:

| Bază de date | Rol |
|---|---|
| `scraper/data_out/products.db` | Date de piață, acces read-only |
| `web/web.db` | Date aplicație (utilizatori, evaluări, anunțuri, favorite, notificări) |

---

## 7. Roluri în aplicație

### Admin
- Dashboard administrativ cu metrici și grafice
- Istoric global al evaluărilor cu filtre
- Acces la toate anunțurile publicate

### Seller
- Evaluează produse și publică anunțuri
- Încarcă imagini pentru anunțuri
- Primește notificări despre interesul cumpărătorilor
- Gestionează propriile anunțuri

### Buyer
- Explorează produse din baza de piață
- Adaugă anunțuri la favorite
- Primește sugestii personalizate pe baza favoritelor

---

## 8. Funcționalități principale

### Evaluarea unui produs

Utilizatorul completează un formular cu titlu, descriere, brand, familie model, RAM, condiție și preț cerut. Aplicația estimează:

- prețul recomandat (bazat pe mediana segmentului de piață);
- scorul de ofertă, interpretat ca atractivitate a prețului pentru cumpărător în raport cu segmentul de piață;
- scorul de depreciere (față de prețul median al produselor noi);
- scorul de atractivitate al anunțului;
- produse similare din baza de date.

### Publicarea unui anunț

Un seller poate publica un anunț pornind de la o evaluare salvată și poate încărca o imagine a produsului. Imaginile sunt salvate în:

```text
web/app/static/uploads/listings/
```

La ștergerea unui anunț, imaginea asociată este ștearsă automat și de pe disc.

### Favorite și recomandări

Buyerii pot salva anunțuri la favorite. Aplicația generează sugestii personalizate pe baza segmentelor de piață preferate (brand + model_family + ram_gb).

### Notificări pentru seller

Sellerii primesc notificări când cumpărători salvează la favorite anunțuri din același segment cu produsele lor. Notificarea include și prețul median estimat din piață pentru segmentul respectiv.

---

## 9. Rularea aplicației web

```powershell
cd C:\Users\User\licenta_2026\web
..\.venv\Scripts\activate
python -m flask --app run.py run
```

Aplicația pornește la: `http://127.0.0.1:5000`

---

## 10. Configurare

Fișierul de configurare: `web/config.py`

| Parametru | Valoare implicită |
|---|---|
| `SECRET_KEY` | `licenta-dev-secret-key` (development) |
| `UPLOAD_FOLDER` | `web/app/static/uploads/listings/` |
| `MAX_CONTENT_LENGTH` | 5 MB |

Pentru producție, setează variabila de mediu `SECRET_KEY`.

---

## 11. Crearea unui cont de admin

```powershell
cd C:\Users\User\licenta_2026\web
..\.venv\Scripts\activate
python -c "from app import create_app; from app.services import set_user_role; app=create_app(); app.app_context().push(); print(set_user_role('email@example.com','admin'))"
```

Înlocuiește `email@example.com` cu adresa contului care trebuie promovat.

---

## 12. Observații privind baza de date

Aplicația creează automat tabelele lipsă din `web.db` prin `db.create_all()`. Dacă se adaugă coloane noi în modele după crearea bazei, este necesară o migrare manuală.

**Exemplu — adăugare coloană `image_filename` dacă lipsește:**

```powershell
python -c "import sqlite3; con=sqlite3.connect('web.db'); cur=con.cursor(); cols=[r[1] for r in cur.execute('PRAGMA table_info(listings)')]; cur.execute('ALTER TABLE listings ADD COLUMN image_filename TEXT') if 'image_filename' not in cols else None; con.commit(); con.close(); print('OK')"
```

---

## 13. Testare

```powershell
cd C:\Users\User\licenta_2026\scraper
..\.venv\Scripts\activate
pytest -q
```

---

## 14. Fișiere excluse din repository

```text
__pycache__/
.pytest_cache/
*.db-shm
*.db-wal
scraper/logs/
scraper/data_out/browser_profile/
web/app/static/uploads/listings/
```

`products.db` poate fi păstrat pentru a permite rularea aplicației fără a relua scrapingul de la zero. Opțional, `web.db` poate fi păstrat dacă se dorește includerea unor utilizatori și anunțuri demonstrative.

---

## 15. Scopul proiectului

Sistemul combină colectarea automată de date, normalizarea informațiilor de piață și o aplicație web cu roluri multiple, pentru a sprijini procesul de evaluare și publicare a anunțurilor de laptopuri second-hand și noi.

Poate fi utilizat pentru:

- estimarea unui preț orientativ bazat pe date reale de piață;
- compararea cu produse similare;
- analiza diferenței dintre prețul cerut și valoarea de piață;
- personalizarea experienței pentru cumpărători;
- informarea vânzătorilor despre interesul existent în platformă;
- monitorizarea activității prin dashboard administrativ.