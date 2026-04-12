"""
Tool handler: create_agent — autonomous agent creation within a department.

CEO/Admin can create agents anywhere. Supervisors can only create in their own department.
Validates max 15 agents per department to prevent runaway creation.
Reuses AgentService for actual creation logic.
"""

from sqlalchemy import func, select

from app.agents.models import Agent, RoleLevel
from app.agents.schemas import AgentCreateInternal
from app.agents.service import AgentService
from app.core.events import Event, event_bus
from app.departments.models import Department
from app.departments.repository import DepartmentRepository
from app.workers.tool_registry import ToolContext, register_tool

# Hard limit — prevents runaway autonomous agent creation within a department
_MAX_AGENTS_PER_DEPARTMENT = 15


@register_tool("create_agent")
async def handle_create_agent(ctx: ToolContext, tool_input: dict) -> dict:
    """Create a new internal agent in a department."""
    name = tool_input.get("name")
    description = tool_input.get("description")
    department_slug = tool_input.get("department_slug")
    role = tool_input.get("role", "agent")
    capabilities = tool_input.get("capabilities", [])

    if not name or not department_slug:
        return {"error": "name and department_slug are required"}

    # Resolve department by slug
    dept_repo = DepartmentRepository(ctx.db, ctx.org_id)
    dept = await dept_repo.get_by_slug(department_slug)
    if dept is None:
        return {"error": f"Department '{department_slug}' not found"}

    # Supervisors can only create agents in their own department
    if ctx.calling_agent_role == RoleLevel.SUPERVISOR:
        if ctx.calling_agent_department_id and ctx.calling_agent_department_id != dept.id:
            return {"error": "Supervisors can only create agents in their own department"}

    # Check hard limit per department
    agent_count_result = await ctx.db.execute(
        select(func.count())
        .select_from(Agent)
        .where(Agent.department_id == dept.id, Agent.organization_id == ctx.org_id)
    )
    current_count = agent_count_result.scalar_one()

    if current_count >= _MAX_AGENTS_PER_DEPARTMENT:
        return {
            "error": f"Department '{department_slug}' already has {current_count} agents (max {_MAX_AGENTS_PER_DEPARTMENT})",
            "suggestion": "Consider repurposing existing agents or creating a new department",
        }

    # Resolve role_id — look up the role by level name
    from app.agents.repository import AgentRepository
    agent_repo = AgentRepository(ctx.db, ctx.org_id)

    role_level = RoleLevel.AGENT if role == "agent" else RoleLevel.SUPERVISOR
    roles = await agent_repo.list_roles()
    matching_role = next((r for r in roles if r.level == role_level), None)
    role_id = matching_role.id if matching_role else None

    # Find the department supervisor to set as this agent's supervisor
    supervisor_id = dept.head_agent_id

    # Create agent via existing service
    service = AgentService(ctx.db, ctx.org_id)

    try:
        agent_response = await service.create_internal_agent(
            AgentCreateInternal(
                name=name,
                description=description,
                department_id=dept.id,
                role_id=role_id,
                supervisor_id=supervisor_id,
                capabilities=capabilities,
                # Placeholder prompt — generate_prompt tool will set the real one
                system_prompt=f"Eres {name}. {description or ''}",
                model_name="claude-sonnet-4-20250514",
                temperature=0.7,
                max_tokens=4096,
            )
        )
    except Exception as exc:
        return {"error": f"Failed to create agent: {str(exc)[:200]}"}

    # Store provenance — who created this agent and why
    from sqlalchemy import select as sa_select
    created_agent_result = await ctx.db.execute(
        sa_select(Agent).where(Agent.id == agent_response.id)
    )
    created_agent = created_agent_result.scalar_one_or_none()
    if created_agent:
        created_agent.created_by_agent_id = ctx.calling_agent_id
        created_agent.creation_reason = f"Creado por {ctx.calling_agent_name}: {description or name}"
        await ctx.db.flush()

    # Create notification for human visibility
    from app.notifications.models import Notification, NotificationType
    notification = Notification(
        organization_id=ctx.org_id,
        agent_id=agent_response.id,
        title=f"Nuevo agente autónomo: {name}",
        body=f"**{ctx.calling_agent_name}** creó al agente **{name}** en el departamento **{dept.name}**.",
        notification_type=NotificationType.AGENT_CREATED,
        action_url=f"/agents/{agent_response.id}",
        metadata_={
            "created_by_agent": ctx.calling_agent_name,
            "department": department_slug,
            "capabilities": capabilities,
        },
    )
    ctx.db.add(notification)
    await ctx.db.flush()

    # Emit SSE event
    await event_bus.publish(Event(
        type="agent.created",
        data={
            "agent_id": str(agent_response.id),
            "name": agent_response.name,
            "slug": agent_response.slug,
            "department": department_slug,
            "created_by_agent": ctx.calling_agent_name,
            "autonomous": True,
        },
    ))

    return {
        "success": True,
        "agent_id": str(agent_response.id),
        "name": agent_response.name,
        "slug": agent_response.slug,
        "department": department_slug,
        "role": role,
        "note": "Agent created with placeholder prompt. Use generate_prompt to create a specialized system prompt.",
    }
