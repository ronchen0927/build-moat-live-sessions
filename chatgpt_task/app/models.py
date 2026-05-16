from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class Job(BaseModel):
    id: int
    description: str
    scheduled_at: datetime
    hour_bucket: str  # e.g. "2026-05-16-06"
    status: Literal["pending", "queued", "running", "completed", "cancelled"]
    created_at: datetime
    completed_at: Optional[datetime] = None
