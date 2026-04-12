"""
Read-only tools for querying org structure — departments and agents.

Available to all roles. These let Claude understand the current state
of the organization before deciding what to create or delegate.
"""

from sqlalchemy import func, select

from app.agents.models import Agent
from app.departments.models import Department
from app.departments.repository import DepartmentRepository
from app.workers.tool_registry import ToolContext, register_tool


@register_tool("list_departments")
async def handle_list_departments(ctx: ToolContext, tool_input: dict) -> dict:
    """List all departments in the org with agent counts."""
    repo = DepartmentRepository(ctx.db, ctx.org_id)

    result = await ctx.db.execute(
        select(Department)
        .where(Department.organization_id == ctx.org_id)
        .order_by(Department.name)
    )
    departments = list(result.scalars().all())

    dept_list = []
    for dept in departments:
        agent_count = await repo.count_agents(dept.id)
        dept_list.append({
            "name": dept.name,
            "slug": dept.slug,
            "description": dept.description,
            "agent_count": agent_count,
            "head_agent_id": str(dept.head_agent_id) if dept.head_agent_id else None,
        })

    return {
        "success": True,
        "department_count": len(dept_list),
        "departments": dept_list,
    }


@register_tool("list_department_agents")
async def handle_list_department_agents(ctx: ToolContext, tool_input: dict) -> dict:
    """List agents in a specific department with capabilities and status."""
    department_slug = tool_input.get("department_slug")
    if not department_slug:
        return {"error": "department_slug is required"}

    # Look up department by slug
    repo = DepartmentRepository(ctx.db, ctx.org_id)
    dept = await repo.get_by_slug(department_slug)
    if dept is None:
        return {"error": f"Department '{department_slug}' not found"}

    # Supervisors can only query their own department
    from app.agents.models import RoleLevel
    if ctx.calling_agent_role == RoleLevel.SUPERVISOR:
        if ctx.calling_agent_department_id and ctx.calling_agent_department_id != dept.id:
            return {"error": "Supervisors can only query agents in their own department"}

    agents = await repo.get_agents_in_department(dept.id)

    agent_list = []
    for agent in agents:
        agent_list.append({
            "name": agent.name,
            "slug": agent.slug,
            "description": agent.description,
            "status": agent.status.value if agent.status else "unknown",
            "capabilities": agent.capabilities or [],
        })

    return {
        "success": True,
        "department": department_slug,
        "agent_count": len(agent_list),
        "agents": agent_list,
    }
