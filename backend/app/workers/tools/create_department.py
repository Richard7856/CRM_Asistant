"""
Tool handler: create_department — autonomous department creation.

Only CEO/Admin and Manager roles can create departments.
Validates max 20 departments per org to prevent runaway creation.
Reuses DepartmentService for the actual creation logic.
"""

from sqlalchemy import func, select

from app.core.events import Event, event_bus
from app.departments.models import Department
from app.departments.schemas import DepartmentCreate
from app.departments.service import DepartmentService
from app.workers.tool_registry import ToolContext, register_tool

# Hard limit — prevents runaway autonomous department creation
_MAX_DEPARTMENTS_PER_ORG = 20


@register_tool("create_department")
async def handle_create_department(ctx: ToolContext, tool_input: dict) -> dict:
    """Create a new department in the organization."""
    name = tool_input.get("name")
    description = tool_input.get("description")

    if not name:
        return {"error": "name is required"}

    # Check hard limit before creating
    count_result = await ctx.db.execute(
        select(func.count())
        .select_from(Department)
        .where(Department.organization_id == ctx.org_id)
    )
    current_count = count_result.scalar_one()

    if current_count >= _MAX_DEPARTMENTS_PER_ORG:
        return {
            "error": f"Organization already has {current_count} departments (max {_MAX_DEPARTMENTS_PER_ORG})",
            "suggestion": "Consider consolidating existing departments before creating new ones",
        }

    # Reuse existing service — handles slug generation, duplicate checking, etc.
    service = DepartmentService(ctx.db, ctx.org_id)

    try:
        dept_response = await service.create_department(
            DepartmentCreate(name=name, description=description)
        )
    except Exception as exc:
        return {"error": f"Failed to create department: {str(exc)[:200]}"}

    # Emit SSE event so the frontend sees the new department immediately
    await event_bus.publish(Event(
        type="department.created",
        data={
            "department_id": str(dept_response.id),
            "name": dept_response.name,
            "slug": dept_response.slug,
            "created_by_agent": ctx.calling_agent_name,
            "autonomous": True,
        },
    ))

    return {
        "success": True,
        "department_id": str(dept_response.id),
        "name": dept_response.name,
        "slug": dept_response.slug,
    }
