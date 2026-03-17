import csv
import sqlite3
from pathlib import Path

from app.config.base import DB_PATH

EXPORT_DIR = Path("data_out/exports")
QUALITY_CSV = EXPORT_DIR / "results_dataset_quality.csv"
PRICE_SUMMARY_CSV = EXPORT_DIR / "results_price_summary.csv"


def ensure_export_dir():
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)


def pct(n, d):
    return round(100 * n / d, 1) if d else 0.0


def write_csv(path, fieldnames, rows):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_quality_summary(cur):
    products_total = cur.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    products_clean_total = cur.execute("SELECT COUNT(*) FROM products_clean").fetchone()[0]

    by_source = dict(cur.execute("""
        SELECT source, COUNT(*)
        FROM products
        GROUP BY source
    """).fetchall())

    posted_at_not_null = cur.execute("""
        SELECT COUNT(*)
        FROM products
        WHERE posted_at IS NOT NULL
    """).fetchone()[0]

    publi24_location_not_null = cur.execute("""
        SELECT COUNT(*)
        FROM products
        WHERE source='publi24' AND location IS NOT NULL
    """).fetchone()[0]

    pcgarage_model_guess_not_null = cur.execute("""
        SELECT COUNT(*)
        FROM products
        WHERE source='pcgarage' AND model_guess IS NOT NULL
    """).fetchone()[0]

    condition_not_null = cur.execute("""
        SELECT COUNT(*)
        FROM products
        WHERE condition IS NOT NULL
    """).fetchone()[0]

    price_ron_cov = cur.execute("""
        SELECT COUNT(*)
        FROM products_clean
        WHERE price_ron IS NOT NULL
    """).fetchone()[0]

    title_std_cov = cur.execute("""
        SELECT COUNT(*)
        FROM products_clean
        WHERE title_std IS NOT NULL
    """).fetchone()[0]

    model_norm_cov = cur.execute("""
        SELECT COUNT(*)
        FROM products_clean
        WHERE model_norm IS NOT NULL
    """).fetchone()[0]

    cpu_guess_cov = cur.execute("""
        SELECT COUNT(*)
        FROM products_clean
        WHERE cpu_guess IS NOT NULL
    """).fetchone()[0]

    ram_gb_cov = cur.execute("""
        SELECT COUNT(*)
        FROM products_clean
        WHERE ram_gb IS NOT NULL
    """).fetchone()[0]

    storage_guess_cov = cur.execute("""
        SELECT COUNT(*)
        FROM products_clean
        WHERE storage_guess IS NOT NULL
    """).fetchone()[0]

    gpu_guess_cov = cur.execute("""
        SELECT COUNT(*)
        FROM products_clean
        WHERE gpu_guess IS NOT NULL
    """).fetchone()[0]

    screen_in_cov = cur.execute("""
        SELECT COUNT(*)
        FROM products_clean
        WHERE screen_in IS NOT NULL
    """).fetchone()[0]

    snapshots = cur.execute("SELECT COUNT(*) FROM price_snapshots").fetchone()[0]
    distinct_urls = cur.execute("SELECT COUNT(DISTINCT url) FROM products").fetchone()[0]

    rows = [
        {
            "metric": "products_total",
            "value": products_total,
            "notes": "Total produse brute"
        },
        {
            "metric": "products_publi24",
            "value": by_source.get("publi24", 0),
            "notes": "Produse marketplace"
        },
        {
            "metric": "products_pcgarage",
            "value": by_source.get("pcgarage", 0),
            "notes": "Produse retail"
        },
        {
            "metric": "products_clean_total",
            "value": products_clean_total,
            "notes": "Produse în tabelul normalizat"
        },
        {
            "metric": "posted_at_not_null",
            "value": posted_at_not_null,
            "notes": "Doar marketplace trebuie să aibă posted_at"
        },
        {
            "metric": "publi24_location_not_null",
            "value": f"{publi24_location_not_null}/{by_source.get('publi24', 0)} ({pct(publi24_location_not_null, by_source.get('publi24', 0))}%)",
            "notes": "Coverage locație marketplace"
        },
        {
            "metric": "pcgarage_model_guess_not_null",
            "value": f"{pcgarage_model_guess_not_null}/{by_source.get('pcgarage', 0)} ({pct(pcgarage_model_guess_not_null, by_source.get('pcgarage', 0))}%)",
            "notes": "Coverage model_guess retail"
        },
        {
            "metric": "condition_not_null",
            "value": f"{condition_not_null}/{products_total} ({pct(condition_not_null, products_total)}%)",
            "notes": "Coverage condiție brută"
        },
        {
            "metric": "price_ron_coverage",
            "value": f"{price_ron_cov}/{products_clean_total} ({pct(price_ron_cov, products_clean_total)}%)",
            "notes": "Coverage preț standardizat"
        },
        {
            "metric": "title_std_coverage",
            "value": f"{title_std_cov}/{products_clean_total} ({pct(title_std_cov, products_clean_total)}%)",
            "notes": "Coverage titlu standardizat"
        },
        {
            "metric": "model_norm_coverage",
            "value": f"{model_norm_cov}/{products_clean_total} ({pct(model_norm_cov, products_clean_total)}%)",
            "notes": "Coverage model standardizat"
        },
        {
            "metric": "cpu_guess_coverage",
            "value": f"{cpu_guess_cov}/{products_clean_total} ({pct(cpu_guess_cov, products_clean_total)}%)",
            "notes": "Coverage CPU extras"
        },
        {
            "metric": "ram_gb_coverage",
            "value": f"{ram_gb_cov}/{products_clean_total} ({pct(ram_gb_cov, products_clean_total)}%)",
            "notes": "Coverage RAM extras"
        },
        {
            "metric": "storage_guess_coverage",
            "value": f"{storage_guess_cov}/{products_clean_total} ({pct(storage_guess_cov, products_clean_total)}%)",
            "notes": "Coverage storage extras"
        },
        {
            "metric": "gpu_guess_coverage",
            "value": f"{gpu_guess_cov}/{products_clean_total} ({pct(gpu_guess_cov, products_clean_total)}%)",
            "notes": "Coverage GPU extras"
        },
        {
            "metric": "screen_in_coverage",
            "value": f"{screen_in_cov}/{products_clean_total} ({pct(screen_in_cov, products_clean_total)}%)",
            "notes": "Coverage diagonală ecran"
        },
        {
            "metric": "snapshots_total",
            "value": snapshots,
            "notes": "Număr snapshot-uri de preț"
        },
        {
            "metric": "distinct_urls",
            "value": distinct_urls,
            "notes": "URL-uri distincte"
        },
        {
            "metric": "dataset_status",
            "value": "READY",
            "notes": "Status final pentru datasetul pilot"
        },
    ]
    return rows


def build_price_summary(cur):
    robust_rows = cur.execute("""
        SELECT
            brand_norm,
            model_family,
            used_n,
            new_n,
            used_median_ron,
            new_median_ron,
            used_to_new_ratio,
            discount_pct_vs_new,
            robust_group
        FROM (
            SELECT
                brand_norm,
                model_family,
                used_n,
                new_n,
                used_median_ron,
                new_median_ron,
                used_to_new_ratio,
                discount_pct_vs_new,
                robust_group
            FROM (
                SELECT *
                FROM (
                    SELECT 1
                )
            )
        )
    """).fetchall()
    # placeholder: citim din CSV-ul deja exportat
    return []


def main():
    ensure_export_dir()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    quality_rows = build_quality_summary(cur)
    write_csv(
        QUALITY_CSV,
        fieldnames=["metric", "value", "notes"],
        rows=quality_rows
    )

    print("=== RESULTS SUMMARY EXPORT ===")
    print("DB_PATH:", DB_PATH)
    print("wrote:", QUALITY_CSV)
    print("price summary table will be exported from robust_price_groups.csv directly")

    conn.close()


if __name__ == "__main__":
    main()