"""
Tool Registry — centralized dispatch for autonomous agent tools.

Each tool handler registers itself via @register_tool("name").
The executor calls execute_tool() when Claude returns a tool_use block,
passing a ToolContext with the DB session, org scope, and calling agent info.

This keeps tool logic decoupled from the executor — adding a new tool
is just a decorated async function, no executor changes needed.
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.models import RoleLevel

logger = logging.getLogger(__name__)

# Type alias for tool handler functions
ToolHandler = Callable[["ToolContext", dict], Coroutine[Any, Any, dict]]

# Global registry: tool_name -> handler function
_registry: dict[str, ToolHandler] = {}

# Rate limit tracking: (org_id, agent_id, tool_name) -> list of timestamps
_rate_limit_log: dict[tuple[str, str, str], list[float]] = {}

# Max autonomous creations per agent per hour (prevents runaway loops)
_RATE_LIMIT_PER_HOUR = 3
_RATE_LIMIT_WINDOW_SECONDS = 3600


@dataclass
class ToolContext:
    """Everything a tool handler needs to do its work safely."""
    db: AsyncSession
    org_id: uuid.UUID
    calling_agent_id: uuid.UUID
    calling_agent_role: RoleLevel
    # Department scope — supervisors can only act within their department
    calling_agent_department_id: uuid.UUID | None = None
    # Metadata for activity logging
    calling_agent_name: str = ""
    task_id: uuid.UUID | None = None


def register_tool(name: str):
    """
    Decorator to register an async function as a tool handler.

    Usage:
        @register_tool("create_department")
        async def handle_create_department(ctx: ToolContext, input: dict) -> dict:
            ...
    """
    def decorator(func: ToolHandler) -> ToolHandler:
        if name in _registry:
            logger.warning("Tool '%s' registered twice — overwriting previous handler", name)
        _registry[name] = func
        logger.debug("Registered tool: %s", name)
        return func
    return decorator


def get_registered_tools() -> list[str]:
    """Return names of all registered tools (useful for debugging)."""
    return list(_registry.keys())


async def execute_tool(name: str, tool_input: dict, ctx: ToolContext) -> dict:
    """
    Look up a tool by name and execute it with the given context.

    Returns a dict with the tool result (success or error).
    Applies rate limiting for creation tools to prevent runaway agent loops.
    """
    handler = _registry.get(name)
    if handler is None:
        return {"error": f"Tool '{name}' not found in registry", "available_tools": get_registered_tools()}

    # Rate limit creation tools — query/read tools are unlimited
    if _is_creation_tool(name):
        if not _check_rate_limit(ctx.org_id, ctx.calling_agent_id, name):
            return {
                "error": f"Rate limit exceeded: max {_RATE_LIMIT_PER_HOUR} '{name}' calls per hour per agent",
                "retry_after_seconds": _RATE_LIMIT_WINDOW_SECONDS,
            }

    try:
        start = time.time()
        result = await handler(ctx, tool_input)
        elapsed_ms = int((time.time() - start) * 1000)

        logger.info(
            "Tool '%s' executed by agent %s in %dms (org %s)",
            name, ctx.calling_agent_name or ctx.calling_agent_id, elapsed_ms, ctx.org_id,
        )
        result["_elapsed_ms"] = elapsed_ms
        return result

    except Exception as exc:
        logger.error("Tool '%s' failed: %s", name, exc, exc_info=True)
        return {"error": f"Tool execution failed: {str(exc)[:300]}"}


def _is_creation_tool(name: str) -> bool:
    """Creation tools are rate-limited to prevent runaway autonomous loops."""
    return name in {"create_department", "create_agent", "generate_prompt"}


def _check_rate_limit(org_id: uuid.UUID, agent_id: uuid.UUID, tool_name: str) -> bool:
    """
    Returns True if the call is allowed, False if rate limited.
    Tracks timestamps in memory — resets if the process restarts (acceptable for MVP).
    """
    key = (str(org_id), str(agent_id), tool_name)
    now = time.time()
    cutoff = now - _RATE_LIMIT_WINDOW_SECONDS

    # Clean old entries
    timestamps = _rate_limit_log.get(key, [])
    timestamps = [t for t in timestamps if t > cutoff]

    if len(timestamps) >= _RATE_LIMIT_PER_HOUR:
        _rate_limit_log[key] = timestamps
        return False

    timestamps.append(now)
    _rate_limit_log[key] = timestamps
    return True
