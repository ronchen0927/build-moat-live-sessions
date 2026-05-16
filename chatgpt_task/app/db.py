import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "jobs.db"

_local = threading.local()


def get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn"):
        conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        _local.conn = conn
    return _local.conn


def init_db() -> None:
    conn = get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            description  TEXT    NOT NULL,
            scheduled_at TEXT    NOT NULL,
            hour_bucket  TEXT    NOT NULL,
            status       TEXT    NOT NULL DEFAULT 'pending',
            created_at   TEXT    NOT NULL,
            completed_at TEXT
        )
    """)
    # Equality lookup on bucket + status — O(1) per scan tick
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_jobs_bucket_status ON jobs(hour_bucket, status)"
    )
    conn.commit()
