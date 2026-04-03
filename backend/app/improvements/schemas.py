from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.improvements.models import ImprovementStatus
from app.tasks.models import TaskPriority


class ImprovementCreate(BaseModel):
    agent_id: uuid.UUID
    identified_by: uuid.UUID | None = None
    category: str = Field(..., min_length=1, max_length=100)
    title: str = Field(..., min_length=1, max_length=300)
    description: str
    evidence: dict | None = None
    priority: TaskPriority = TaskPriority.MEDIUM


class ImprovementUpdate(BaseModel):
    status: ImprovementStatus | None = None
    resolution: str | None = None
    priority: TaskPriority | None = None


class ImprovementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    identified_by: uuid.UUID | None = None
    category: str
    title: str
    description: str
    evidence: dict = {}
    status: ImprovementStatus
    priority: TaskPriority
    resolution: str | None = None
    created_at: datetime
    updated_at: datetime
