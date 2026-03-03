import sqlite3

db_path = "data_out/products.db"
with sqlite3.connect(db_path) as conn:
    conn.execute("VACUUM;")
    conn.execute("ANALYZE;")
print("OK")