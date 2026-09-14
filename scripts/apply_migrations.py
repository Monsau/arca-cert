"""Apply versioned SQL migrations to the configured database."""
import glob
import os
import sqlite3
import sys
from pathlib import Path

DB_URL = os.environ.get("DATABASE_URL", "sqlite:///./data.db")


def apply_sqlite(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    for sql_file in sorted(glob.glob("migrations/*.sql")):
        print(f"  {sql_file}")
        conn.executescript(Path(sql_file).read_text(encoding="utf-8"))
    conn.commit()
    conn.close()


def main() -> int:
    print(f"Applying migrations to {DB_URL} ...")
    if DB_URL.startswith("sqlite:///"):
        apply_sqlite(DB_URL[len("sqlite:///"):])
    else:
        print("PostgreSQL migrations require psql wiring (placeholder).")
        return 1
    print("Migrations applied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
