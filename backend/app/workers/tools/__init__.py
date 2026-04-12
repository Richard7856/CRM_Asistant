"""
Autonomous agent tools package.

Importing this package registers all tool handlers with the tool_registry.
The agent_executor imports this at startup to ensure all tools are available.

Each module contains one @register_tool handler that reuses existing services
for the actual business logic — the handlers are thin wrappers that add
validation, rate limiting context, and SSE events.
"""

# Import all tool modules so their @register_tool decorators execute
from app.workers.tools import (  # noqa: F401
    assign_task,
    create_agent,
    create_department,
    generate_prompt,
    query_org,
)
