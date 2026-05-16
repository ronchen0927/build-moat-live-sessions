from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Job:
    id: int
    description: str
    scheduled_at: datetime
    hour_bucket: str  # e.g. "2026-05-16-06"
    status: str       # pending | queued | running | completed | cancelled
    created_at: datetime
    completed_at: Optional[datetime] = None
