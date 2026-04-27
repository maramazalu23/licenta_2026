$ProjectRoot = "C:\Users\User\licenta_2026"
$ScraperDir = "$ProjectRoot\scraper"
$Python = "$ProjectRoot\.venv\Scripts\python.exe"

Set-Location $ScraperDir

Write-Host "=== Pornire scraping zilnic ==="

Write-Host "1. Publi24..."
& $Python run.py publi24 --category laptopuri --pages 2 --max-products 20

Write-Host "2. PCGarage..."
& $Python run.py pcgarage --category laptopuri --pages 1 --max-products 20

Write-Host "3. Reconstruire dataset analiza..."
& $Python -m scripts.build_analysis_dataset

Write-Host "4. Compactare baza de date..."
& $Python -m scripts.vacuum_db

Write-Host "=== Scraping zilnic finalizat ==="