from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.activities.models import LogLevel


class ActivityCreate(BaseModel):
    agent_id: uuid.UUID
    task_id: uuid.UUID | None = None
    action: str = Field(..., min_length=1, max_length=200)
    level: LogLevel = LogLevel.INFO
    summary: str | None = None
    details: dict | None = None


class ActivityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    task_id: uuid.UUID | None = None
    action: str
    level: LogLevel
    summary: str | None = None
    details: dict = {}
    occurred_at: datetime


class ActivitySummary(BaseModel):
    level: LogLevel
    count: int
