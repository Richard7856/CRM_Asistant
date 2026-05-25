"""
MCP Router endpoint — the gateway every user request flows through.

Responsibilities (per the architecture established in ROADMAP V3.1):
1. Identify the user (already done by JWT dependency)
2. Resolve their scope (agents + tools they can invoke)
3. Audit the request (MCP_ROUTE_REQUESTED with query hash)
4. Find the supervisor agent of the user's department
5. Create a task assigned to that supervisor + dispatch delegation
6. Return 202 with task_id (client polls or listens to SSE for the result)

What the Router does NOT do:
- Decompose tasks (the supervisor's job — supervisor_delegator.py)
- Decide plan-vs-execute (CEO Agent's job — P0.6, P1.2)
- Make cognitive decisions (the Router is purely access control + dispatch)

Permissions are revocable instantly — scope is queried fresh from DB on every
call, no caching.
"""

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.agents.models import Agent, AgentStatus, Role, RoleLevel
from app.audit.models import AuditEventType, AuditResult
from app.audit.service import log_audit_event
from app.auth.dependencies import get_current_user
from app.auth.models import User, UserRole
from app.core.database import get_db
from app.departments.models import Department
from app.mcp.schemas import RouteRequest, RouteResponse
from app.mcp.service import ScopeService
from app.tasks.models import Task, TaskPriority, TaskStatus
from app.workers.supervisor_delegator import delegate_task_background

router = APIRouter()


@router.post("/route", response_model=RouteResponse, status_code=status.HTTP_202_ACCEPTED)
async def route_request(
    body: RouteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """
    Main MCP Router entrypoint.

    Returns 202 Accepted with a task_id. The frontend listens for SSE events
    (task.completed / task.failed) to know when the work is done.

    Failure modes:
    - 400: user is OWNER/ADMIN without department and didn't specify target_department_id
    - 403: user has no scope (member without dept assigned, or empty dept scope)
    - 503: department has no supervisor configured — admin must fix
    """
    # 1) Resolve user's scope (fresh from DB — no cache, revokes effective instantly)
    scope_service = ScopeService(db, user.organization_id, actor_user_id=user.id)
    scope = await scope_service.resolve_scope_for_user(user)

    # 2) Determine target department
    if body.target_department_id is not None:
        # Only owners/admins can target a department they don't belong to
        if user.role not in (UserRole.OWNER, UserRole.ADMIN) and body.target_department_id != user.department_id:
            await log_audit_event(
                db, organization_id=user.organization_id,
                event_type=AuditEventType.MCP_ROUTE_DENIED,
                actor_user_id=user.id,
                result=AuditResult.DENIED,
                input_payload=body.query,
                context={"reason": "member_cannot_target_other_department",
                         "requested_dept_id": str(body.target_department_id)},
            )
            raise HTTPException(
                status_code=403,
                detail="Solo OWNER/ADMIN pueden ejecutar en un departamento distinto al suyo",
            )
        target_dept_id = body.target_department_id
    elif user.department_id is not None:
        target_dept_id = user.department_id
    elif user.role in (UserRole.OWNER, UserRole.ADMIN):
        # Owner/admin without dept must specify target
        await log_audit_event(
            db, organization_id=user.organization_id,
            event_type=AuditEventType.MCP_ROUTE_DENIED,
            actor_user_id=user.id,
            result=AuditResult.DENIED,
            input_payload=body.query,
            context={"reason": "owner_admin_missing_target_department"},
        )
        raise HTTPException(
            status_code=400,
            detail="Especifica target_department_id — eres OWNER/ADMIN sin departamento asignado",
        )
    else:
        # Member/viewer without department — can't use the Router
        await log_audit_event(
            db, organization_id=user.organization_id,
            event_type=AuditEventType.MCP_ROUTE_DENIED,
            actor_user_id=user.id,
            result=AuditResult.DENIED,
            input_payload=body.query,
            context={"reason": "member_without_department"},
        )
        raise HTTPException(
            status_code=403,
            detail="No estás asignado a ningún departamento. Pide a tu admin que te asigne uno.",
        )

    # 3) Verify the target dept exists and belongs to our org
    dept_result = await db.execute(
        select(Department).where(
            Department.id == target_dept_id,
            Department.organization_id == user.organization_id,
        )
    )
    department = dept_result.scalar_one_or_none()
    if department is None:
        # Either the dept doesn't exist or belongs to another org
        await log_audit_event(
            db, organization_id=user.organization_id,
            event_type=AuditEventType.MCP_ROUTE_DENIED,
            actor_user_id=user.id,
            result=AuditResult.DENIED,
            input_payload=body.query,
            context={"reason": "department_not_found",
                     "requested_dept_id": str(target_dept_id)},
        )
        raise HTTPException(status_code=404, detail=f"Departamento {target_dept_id} no encontrado")

    # 4) Find the supervisor of this department
    supervisor = await _find_department_supervisor(db, department.id, user.organization_id)
    if supervisor is None:
        await log_audit_event(
            db, organization_id=user.organization_id,
            event_type=AuditEventType.MCP_ROUTE_DENIED,
            actor_user_id=user.id,
            result=AuditResult.DENIED,
            input_payload=body.query,
            context={"reason": "no_supervisor_in_department",
                     "department_id": str(department.id),
                     "department_name": department.name},
        )
        raise HTTPException(
            status_code=503,
            detail=f"El departamento {department.name} no tiene un supervisor configurado",
        )

    # 5) For members: verify the supervisor is in their scope.
    #    (Owners/admins bypass this — is_org_wide=True allows anything)
    if not scope.can_invoke_agent(supervisor.id):
        await log_audit_event(
            db, organization_id=user.organization_id,
            event_type=AuditEventType.MCP_ROUTE_DENIED,
            actor_user_id=user.id,
            result=AuditResult.DENIED,
            input_payload=body.query,
            context={"reason": "supervisor_not_in_user_scope",
                     "supervisor_id": str(supervisor.id),
                     "department_id": str(department.id)},
        )
        raise HTTPException(
            status_code=403,
            detail="No tienes permisos para invocar al supervisor de este departamento. "
                   "Pide al admin que agregue el supervisor a tu scope.",
        )

    # 6) Create the task assigned to the supervisor
    # task.created_by is FK to agents.id (not users) — this task originates from a
    # human user, so we leave it NULL. The audit_log entry below captures the user
    # in actor_user_id, which provides full traceability.
    task = Task(
        title=_summarize_query(body.query),
        description=body.query,
        status=TaskStatus.ASSIGNED,
        priority=TaskPriority.MEDIUM,
        assigned_to=supervisor.id,
        department_id=department.id,
        organization_id=user.organization_id,
    )
    db.add(task)
    await db.flush()

    # 7) Audit the successful route — query is hashed (privacy)
    await log_audit_event(
        db, organization_id=user.organization_id,
        event_type=AuditEventType.MCP_ROUTE_REQUESTED,
        resource_type="task", resource_id=task.id,
        actor_user_id=user.id,
        result=AuditResult.SUCCESS,
        input_payload=body.query,
        context={
            "department_id": str(department.id),
            "department_name": department.name,
            "supervisor_id": str(supervisor.id),
            "supervisor_name": supervisor.name,
            "scope_org_wide": scope.is_org_wide,
            "scope_agent_count": len(scope.agent_ids),
            "scope_tool_count": len(scope.tool_names),
        },
    )

    # 8) Dispatch the supervisor delegation in the background.
    #    The asyncio.create_task schedules but doesn't execute immediately —
    #    the event loop runs the coroutine AFTER this endpoint returns and
    #    get_db has committed the transaction. By the time the background task
    #    opens its own DB session, the row is visible.
    asyncio.create_task(
        delegate_task_background(task.id),
        name=f"mcp-route-task-{task.id}",
    )

    return RouteResponse(
        task_id=task.id,
        department_id=department.id,
        supervisor_agent_id=supervisor.id,
        supervisor_agent_name=supervisor.name,
        message="Petición aceptada. El supervisor del departamento la está procesando.",
    )


async def _find_department_supervisor(
    db: AsyncSession, department_id: uuid.UUID, org_id: uuid.UUID
) -> Agent | None:
    """
    Returns the active supervisor/manager of a department, if any.

    Strategy:
    - Prefer the department.head_agent_id if set and the agent is supervisor+
    - Otherwise, the first SUPERVISOR or MANAGER agent in the dept
    - Excludes agents in ERROR or OFFLINE status
    """
    # Try head_agent first
    head_result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.role))
        .join(Department, Department.head_agent_id == Agent.id)
        .where(
            Department.id == department_id,
            Department.organization_id == org_id,
            Agent.status.notin_([AgentStatus.ERROR, AgentStatus.OFFLINE]),
        )
    )
    head = head_result.scalar_one_or_none()
    if head and head.role and head.role.level in (RoleLevel.SUPERVISOR, RoleLevel.MANAGER, RoleLevel.ADMIN):
        return head

    # Fallback: any supervisor in the dept
    fallback_result = await db.execute(
        select(Agent)
        .options(selectinload(Agent.role))
        .join(Role, Role.id == Agent.role_id)
        .where(
            Agent.department_id == department_id,
            Agent.organization_id == org_id,
            Agent.status.notin_([AgentStatus.ERROR, AgentStatus.OFFLINE]),
            Role.level.in_([RoleLevel.SUPERVISOR, RoleLevel.MANAGER, RoleLevel.ADMIN]),
        )
        .limit(1)
    )
    return fallback_result.scalar_one_or_none()


def _summarize_query(query: str, max_len: int = 100) -> str:
    """Generate a task title from the first sentence (or first N chars) of the query."""
    first_line = query.strip().split("\n", 1)[0]
    if len(first_line) <= max_len:
        return first_line
    return first_line[:max_len].rsplit(" ", 1)[0] + "..."
