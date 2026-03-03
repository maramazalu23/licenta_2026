import sqlite3
from app.config.base import DB_PATH

MIN_PRODUCTS_TOTAL = 200          # ajustezi dacă vrei
MIN_PRICE_COVERAGE = 0.90         # 90% să aibă price_ron
MIN_TITLE_STD_COVERAGE = 0.60     # 60% să aibă title_std (realist)
MIN_MODEL_NORM_COVERAGE = 0.50    # 50% să aibă model_norm (îl îmbunătățești în timp)

def pct(n: int, d: int) -> float:
    return 0.0 if d == 0 else n / d

def main() -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # products
    total_products = cur.execute("SELECT COUNT(*) n FROM products").fetchone()["n"]
    by_source = cur.execute(
        "SELECT source, COUNT(*) n FROM products GROUP BY source ORDER BY n DESC"
    ).fetchall()

    # products_clean
    total_clean = cur.execute("SELECT COUNT(*) n FROM products_clean").fetchone()["n"]

    price_ok = cur.execute(
        "SELECT COUNT(*) n FROM products_clean WHERE price_ron IS NOT NULL AND price_ron > 0"
    ).fetchone()["n"]

    title_std_ok = cur.execute(
        "SELECT COUNT(*) n FROM products_clean WHERE title_std IS NOT NULL AND TRIM(title_std) <> ''"
    ).fetchone()["n"]

    model_norm_ok = cur.execute(
        "SELECT COUNT(*) n FROM products_clean WHERE model_norm IS NOT NULL AND TRIM(model_norm) <> ''"
    ).fetchone()["n"]

    cond_dist = cur.execute(
        "SELECT source, condition_norm, COUNT(*) n FROM products_clean GROUP BY source, condition_norm ORDER BY source, n DESC"
    ).fetchall()

    # quick price sanity (catch weird 100x again)
    max_price = cur.execute(
        "SELECT MAX(price_ron) mx FROM products_clean WHERE price_ron IS NOT NULL"
    ).fetchone()["mx"]

    conn.close()

    print("=== READY FOR SITE CHECK ===")
    print("DB_PATH:", DB_PATH)
    print()
    print("products total:", total_products)
    print("products by source:", [(r["source"], r["n"]) for r in by_source])
    print("products_clean total:", total_clean)
    print()
    print(f"price_ron coverage: {price_ok}/{total_clean} = {pct(price_ok,total_clean):.1%}")
    print(f"title_std coverage: {title_std_ok}/{total_clean} = {pct(title_std_ok,total_clean):.1%}")
    print(f"model_norm coverage: {model_norm_ok}/{total_clean} = {pct(model_norm_ok,total_clean):.1%}")
    print()
    print("condition_norm distribution:", [(r["source"], r["condition_norm"], r["n"]) for r in cond_dist])
    print("max price_ron:", max_price)

    failed = False

    if total_products < MIN_PRODUCTS_TOTAL:
        print(f"[FAIL] Too few products: {total_products} < {MIN_PRODUCTS_TOTAL}")
        failed = True

    if pct(price_ok, total_clean) < MIN_PRICE_COVERAGE:
        print(f"[FAIL] Price coverage too low (< {MIN_PRICE_COVERAGE:.0%})")
        failed = True

    if pct(title_std_ok, total_clean) < MIN_TITLE_STD_COVERAGE:
        print(f"[WARN] title_std coverage low (< {MIN_TITLE_STD_COVERAGE:.0%})")

    if pct(model_norm_ok, total_clean) < MIN_MODEL_NORM_COVERAGE:
        print(f"[WARN] model_norm coverage low (< {MIN_MODEL_NORM_COVERAGE:.0%})")

    if max_price is not None and max_price > 200_000:
        print("[FAIL] max price_ron suspiciously high (> 200,000). Possible parsing bug.")
        failed = True

    if failed:
        print("\nRESULT: NOT READY")
        return 2

    print("\nRESULT: READY")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())