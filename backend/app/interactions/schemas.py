from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.interactions.models import InteractionChannel


class InteractionCreate(BaseModel):
    from_agent_id: uuid.UUID
    to_agent_id: uuid.UUID
    channel: InteractionChannel
    task_id: uuid.UUID | None = None
    payload_summary: str | None = None
    payload: dict | None = None
    latency_ms: int | None = None
    success: bool = True


class InteractionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    from_agent_id: uuid.UUID
    to_agent_id: uuid.UUID
    channel: InteractionChannel
    task_id: uuid.UUID | None = None
    payload_summary: str | None = None
    payload: dict | None = None
    latency_ms: int | None = None
    success: bool
    occurred_at: datetime


class GraphNode(BaseModel):
    id: uuid.UUID
    name: str
    department: str | None = None


class GraphEdge(BaseModel):
    source: uuid.UUID
    target: uuid.UUID
    weight: int


class GraphData(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]
