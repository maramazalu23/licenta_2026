import sqlite3
from app.config.base import DB_PATH
db_path = DB_PATH

with sqlite3.connect(db_path) as conn:
    conn.execute("VACUUM;")
    conn.execute("ANALYZE;")
print("OK")