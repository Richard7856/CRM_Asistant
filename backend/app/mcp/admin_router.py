"""
MCP Router scope administration — OWNER/ADMIN only.

Endpoints for managing which agents and tools each department can invoke
through the Router. Backend for the future UI in P2 (multi-user UX).

Path prefix: /api/v1/admin/departments/{dept_id}/scopes
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, get_org_id, require_role
from app.auth.models import User, UserRole
from app.core.database import get_db
from app.core.exceptions import NotFoundError
from app.mcp.schemas import (
    BulkScopeUpdate,
    DepartmentScopeResponse,
    GrantAgentRequest,
    GrantToolRequest,
)
from app.mcp.service import ScopeService

router = APIRouter()

# Only OWNER + ADMIN can modify scopes.
_admin_only = Depends(require_role(UserRole.OWNER, UserRole.ADMIN))


def _get_service(
    db: AsyncSession = Depends(get_db),
    org_id: uuid.UUID = Depends(get_org_id),
    user: User = Depends(get_current_user),
) -> ScopeService:
    return ScopeService(db, org_id, actor_user_id=user.id)


@router.get(
    "/departments/{department_id}/scopes",
    response_model=DepartmentScopeResponse,
    dependencies=[_admin_only],
)
async def get_department_scope(
    department_id: uuid.UUID,
    service: ScopeService = Depends(_get_service),
):
    """Return the current scope (allowed agents + tools) of a department."""
    try:
        dept, agents, tool_names = await service.get_department_scope(department_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return DepartmentScopeResponse(
        department_id=dept.id,
        department_name=dept.name,
        agent_ids=[a.id for a in agents],
        agent_names=[a.name for a in agents],
        tool_names=tool_names,
    )


@router.put(
    "/departments/{department_id}/scopes",
    response_model=DepartmentScopeResponse,
    dependencies=[_admin_only],
)
async def replace_department_scope(
    department_id: uuid.UUID,
    body: BulkScopeUpdate,
    service: ScopeService = Depends(_get_service),
):
    """
    Replace the entire scope of a department in one call.
    Useful for the admin UI's "save all changes" flow.
    """
    try:
        await service.replace_department_scope(
            department_id,
            agent_ids=body.agent_ids,
            tool_names=body.tool_names,
        )
        dept, agents, tool_names = await service.get_department_scope(department_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return DepartmentScopeResponse(
        department_id=dept.id,
        department_name=dept.name,
        agent_ids=[a.id for a in agents],
        agent_names=[a.name for a in agents],
        tool_names=tool_names,
    )


@router.post(
    "/departments/{department_id}/scopes/agents",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_admin_only],
)
async def grant_agent_to_department(
    department_id: uuid.UUID,
    body: GrantAgentRequest,
    service: ScopeService = Depends(_get_service),
):
    """Allow a department to invoke a specific agent."""
    try:
        await service.grant_agent(department_id, body.agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete(
    "/departments/{department_id}/scopes/agents/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_admin_only],
)
async def revoke_agent_from_department(
    department_id: uuid.UUID,
    agent_id: uuid.UUID,
    service: ScopeService = Depends(_get_service),
):
    """Remove an agent from a department's scope. Effective on next request."""
    try:
        await service.revoke_agent(department_id, agent_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post(
    "/departments/{department_id}/scopes/tools",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_admin_only],
)
async def grant_tool_to_department(
    department_id: uuid.UUID,
    body: GrantToolRequest,
    service: ScopeService = Depends(_get_service),
):
    """Allow a department to invoke a specific tool by name."""
    try:
        await service.grant_tool(department_id, body.tool_name)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete(
    "/departments/{department_id}/scopes/tools/{tool_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[_admin_only],
)
async def revoke_tool_from_department(
    department_id: uuid.UUID,
    tool_name: str,
    service: ScopeService = Depends(_get_service),
):
    """Remove a tool from a department's scope. Effective on next request."""
    try:
        await service.revoke_tool(department_id, tool_name)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
