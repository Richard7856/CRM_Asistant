from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DepartmentCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = None
    parent_id: uuid.UUID | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = None
    parent_id: uuid.UUID | None = None
    head_agent_id: uuid.UUID | None = None


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    parent_id: uuid.UUID | None = None
    head_agent_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime
    agent_count: int | None = None


class DepartmentTreeNode(DepartmentResponse):
    children: list[DepartmentTreeNode] = []
