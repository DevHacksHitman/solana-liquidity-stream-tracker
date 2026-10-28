"""Market-data store bootstrap.

Creates and maintains the SQLite schema the stream listener writes into:
one row per observed on-chain trade event, deduplicated by transaction
signature. Also usable as a tiny CLI.

Usage:
    python init_db.py --init     # create the database (default ./data/stream.db)
    python init_db.py --stats    # print row counts
"""

import argparse
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    signature     TEXT UNIQUE,
    slot          INTEGER,
    program_id    TEXT,
    side          TEXT,
    mint          TEXT,
    trader        TEXT,
    token_amount  REAL,
    sol_amount    REAL,
    raw_logs      TEXT,
    metadata_json TEXT,
    fetched_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_trades_mint ON trades(mint);
CREATE INDEX IF NOT EXISTS idx_trades_slot ON trades(slot);
"""

_ROW_COLUMNS = (
    "signature",
    "slot",
    "program_id",
    "side",
    "mint",
    "trader",
    "token_amount",
    "sol_amount",
    "raw_logs",
    "metadata_json",
)


def connect(db_path) -> sqlite3.Connection:
    """Open (and create, if needed) a store with the schema applied."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def init_database(db_path) -> Path:
    conn = connect(db_path)
    conn.close()
    return Path(db_path)


def record_trade(conn: sqlite3.Connection, row: dict) -> bool:
    """Insert one trade row; duplicate signatures are ignored.

    Returns True when a new row was stored.
    """
    cursor = conn.execute(
        f"""
        INSERT OR IGNORE INTO trades ({", ".join(_ROW_COLUMNS)})
        VALUES ({", ".join("?" * len(_ROW_COLUMNS))})
        """,
        tuple(row.get(name) for name in _ROW_COLUMNS),
    )
    return cursor.rowcount > 0


def stats(db_path) -> dict:
    """Row counts and slot bounds for a quick operational sanity check."""
    conn = sqlite3.connect(str(db_path))
    try:
        total = conn.execute("SELECT COUNT(*) FROM trades").fetchone()[0]
        bounds = conn.execute(
            "SELECT MIN(slot), MAX(slot) FROM trades"
        ).fetchone()
    finally:
        conn.close()
    return {"total": total, "first_slot": bounds[0], "last_slot": bounds[1]}


def main() -> int:
    import config

    parser = argparse.ArgumentParser(description="market-data store bootstrap")
    parser.add_argument("--init", action="store_true", help="create the database")
    parser.add_argument("--stats", action="store_true", help="print row counts")
    parser.add_argument("--db", default=str(config.DB_PATH))
    args = parser.parse_args()

    if args.init:
        print(f"OK schema ready: {init_database(args.db)}")
        return 0
    if args.stats:
        print(stats(args.db))
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
