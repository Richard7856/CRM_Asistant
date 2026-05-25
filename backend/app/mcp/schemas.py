"""Pydantic schemas for MCP Router scope management + route endpoint."""

import uuid

from pydantic import BaseModel, Field


class RouteRequest(BaseModel):
    """The user's natural-language request to the MCP Router."""

    query: str = Field(..., min_length=1, max_length=4000)
    # Owners/admins without a department can pick which department's supervisor
    # processes the request. Members are always pinned to their own department.
    target_department_id: uuid.UUID | None = None


class RouteResponse(BaseModel):
    """202 response after the Router dispatches the task to a supervisor."""

    task_id: uuid.UUID
    department_id: uuid.UUID
    supervisor_agent_id: uuid.UUID
    supervisor_agent_name: str
    message: str


class DepartmentScopeResponse(BaseModel):
    """Current scope of a department — what agents and tools it can use."""

    department_id: uuid.UUID
    department_name: str
    agent_ids: list[uuid.UUID]
    agent_names: list[str]
    tool_names: list[str]


class GrantAgentRequest(BaseModel):
    agent_id: uuid.UUID


class GrantToolRequest(BaseModel):
    tool_name: str = Field(..., min_length=1, max_length=100)


class BulkScopeUpdate(BaseModel):
    """Replace the entire scope of a department in one call."""

    agent_ids: list[uuid.UUID] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
