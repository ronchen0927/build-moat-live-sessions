from datetime import datetime
from typing import Optional

from .db import get_conn
from .models import Job


def get_time_bucket(dt: datetime) -> str:
    """Convert a datetime to an hour-granularity bucket key (e.g. '2026-05-16-06')."""
    return dt.strftime("%Y-%m-%d-%H")


def _row_to_job(row) -> Job:
    return Job(
        id=row["id"],
        description=row["description"],
        scheduled_at=datetime.fromisoformat(row["scheduled_at"]),
        hour_bucket=row["hour_bucket"],
        status=row["status"],
        created_at=datetime.fromisoformat(row["created_at"]),
        completed_at=(
            datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
        ),
    )


def create_job(description: str, scheduled_at: datetime) -> Job:
    conn = get_conn()
    cursor = conn.execute(
        "INSERT INTO jobs (description, scheduled_at, hour_bucket, status, created_at)"
        " VALUES (?, ?, ?, 'pending', ?)",
        (
            description,
            scheduled_at.isoformat(),
            get_time_bucket(scheduled_at),
            datetime.utcnow().isoformat(),
        ),
    )
    conn.commit()
    return get_job(cursor.lastrowid)


def get_job(job_id: int) -> Optional[Job]:
    row = get_conn().execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return _row_to_job(row) if row else None


def list_jobs() -> list[Job]:
    rows = get_conn().execute("SELECT * FROM jobs ORDER BY scheduled_at").fetchall()
    return [_row_to_job(r) for r in rows]


def cancel_job(job_id: int) -> Optional[Job]:
    conn = get_conn()
    conn.execute(
        "UPDATE jobs SET status = 'cancelled'"
        " WHERE id = ? AND status IN ('pending', 'queued')",
        (job_id,),
    )
    conn.commit()
    return get_job(job_id)


def mark_queued(job_id: int) -> None:
    conn = get_conn()
    conn.execute("UPDATE jobs SET status = 'queued' WHERE id = ?", (job_id,))
    conn.commit()


def mark_running(job_id: int) -> None:
    conn = get_conn()
    conn.execute("UPDATE jobs SET status = 'running' WHERE id = ?", (job_id,))
    conn.commit()


def mark_completed(job_id: int) -> None:
    conn = get_conn()
    conn.execute(
        "UPDATE jobs SET status = 'completed', completed_at = ? WHERE id = ?",
        (datetime.utcnow().isoformat(), job_id),
    )
    conn.commit()


def find_due_jobs(now: Optional[datetime] = None) -> list[Job]:
    """Return pending jobs whose scheduled_at <= now, using bucket pre-filter."""
    if now is None:
        now = datetime.utcnow()
    current_bucket = get_time_bucket(now)
    rows = get_conn().execute(
        "SELECT * FROM jobs"
        " WHERE status = 'pending'"
        "   AND hour_bucket <= ?"
        "   AND scheduled_at <= ?",
        (current_bucket, now.isoformat()),
    ).fetchall()
    return [_row_to_job(r) for r in rows]
