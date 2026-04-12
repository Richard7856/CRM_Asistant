"""
Tool handler: assign_task — autonomous task assignment to an agent.

Creates a new task and assigns it to a specific agent by slug.
The task is created in ASSIGNED status ready for execution.
Reuses TaskService for the actual creation logic.
"""

from sqlalchemy import select

from app.agents.models import Agent, RoleLevel
from app.core.events import Event, event_bus
from app.tasks.models import TaskPriority
from app.tasks.schemas import TaskCreate
from app.tasks.service import TaskService
from app.workers.tool_registry import ToolContext, register_tool


@register_tool("assign_task")
async def handle_assign_task(ctx: ToolContext, tool_input: dict) -> dict:
    """Create and assign a task to a specific agent."""
    agent_slug = tool_input.get("agent_slug")
    title = tool_input.get("title")
    description = tool_input.get("description")
    priority = tool_input.get("priority", "medium")

    if not agent_slug or not title or not description:
        return {"error": "agent_slug, title, and description are required"}

    # Look up the target agent by slug
    result = await ctx.db.execute(
        select(Agent).where(
            Agent.slug == agent_slug,
            Agent.organization_id == ctx.org_id,
        )
    )
    agent = result.scalar_one_or_none()
    if agent is None:
        return {"error": f"Agent '{agent_slug}' not found"}

    # Supervisors can only assign tasks to agents in their own department
    if ctx.calling_agent_role == RoleLevel.SUPERVISOR:
        if ctx.calling_agent_department_id and agent.department_id != ctx.calling_agent_department_id:
            return {"error": "Supervisors can only assign tasks to agents in their own department"}

    # Map priority string to enum
    priority_map = {
        "low": TaskPriority.LOW,
        "medium": TaskPriority.MEDIUM,
        "high": TaskPriority.HIGH,
        "critical": TaskPriority.CRITICAL,
    }
    task_priority = priority_map.get(priority, TaskPriority.MEDIUM)

    # Create task via existing service
    service = TaskService(ctx.db, ctx.org_id)

    try:
        task_response = await service.create_task(
            TaskCreate(
                title=title,
                description=description,
                priority=task_priority,
                assigned_to=agent.id,
                department_id=agent.department_id,
            )
        )
    except Exception as exc:
        return {"error": f"Failed to create task: {str(exc)[:200]}"}

    # Emit SSE event
    await event_bus.publish(Event(
        type="task.created",
        data={
            "task_id": str(task_response.id),
            "title": title,
            "agent_id": str(agent.id),
            "agent_name": agent.name,
            "created_by_agent": ctx.calling_agent_name,
            "autonomous": True,
        },
    ))

    return {
        "success": True,
        "task_id": str(task_response.id),
        "title": title,
        "assigned_to": agent.name,
        "agent_slug": agent_slug,
        "priority": priority,
        "status": "assigned",
    }
