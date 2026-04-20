import sqlite3
from app.config.base import DB_PATH

# Rulează acest script după multe importuri / upsert-uri / ștergeri,
# pentru a compacta baza de date SQLite (VACUUM) și a actualiza statisticile de query (ANALYZE).

def main():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("VACUUM;")
        conn.execute("ANALYZE;")
    print("OK")

if __name__ == "__main__":
    main()