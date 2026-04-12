from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.tasks.models import TaskPriority, TaskStatus


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=300)
    description: str | None = None
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_to: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    parent_task_id: uuid.UUID | None = None
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assigned_to: uuid.UUID | None = None


class TaskAssign(BaseModel):
    agent_id: uuid.UUID


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None = None
    status: TaskStatus
    priority: TaskPriority
    assigned_to: uuid.UUID | None = None
    created_by: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    parent_task_id: uuid.UUID | None = None
    due_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: dict | None = None
    metadata_: dict = {}
    created_at: datetime
    updated_at: datetime
    assignee_name: str | None = None
    department_name: str | None = None
