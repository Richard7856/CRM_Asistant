from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.metrics.models import MetricPeriod


class MetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    agent_id: uuid.UUID
    period: MetricPeriod
    period_start: datetime
    period_end: datetime
    tasks_completed: int = 0
    tasks_failed: int = 0
    avg_response_ms: float | None = None
    success_rate: float | None = None
    uptime_pct: float | None = None
    token_usage: int = 0
    cost_usd: float = 0
    custom_kpis: dict = {}
    created_at: datetime


class MetricOverview(BaseModel):
    total_agents: int
    active_agents: int
    tasks_completed_today: int
    overall_success_rate: float | None
    avg_response_ms: float | None
    total_cost_today: float


class LeaderboardEntry(BaseModel):
    agent_id: uuid.UUID
    agent_name: str | None = None
    success_rate: float
    tasks_completed: int


class TrendPoint(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    period_start: datetime
    period_end: datetime
    tasks_completed: int = 0
    tasks_failed: int = 0
    success_rate: float | None = None
    avg_response_ms: float | None = None
    token_usage: int = 0
    cost_usd: float = 0


class TrendResponse(BaseModel):
    agent_id: uuid.UUID
    period: MetricPeriod
    data: list[TrendPoint]


class DailyTaskPoint(BaseModel):
    date: str
    completed: int
    failed: int


class TopAgentEntry(BaseModel):
    agent_id: uuid.UUID
    agent_name: str
    tasks_completed: int
    success_rate: float
    cost_usd: float


class MetricSummary(BaseModel):
    total_tasks_completed: int
    total_tasks_failed: int
    avg_success_rate: float | None
    avg_response_ms: float | None
    total_cost_usd: float
    total_token_usage: int
    agents_measured: int
    daily_tasks: list[DailyTaskPoint] = []
    top_agents: list[TopAgentEntry] = []
    tasks_by_status: dict[str, int] = {}
    agents_by_status: dict[str, int] = {}
