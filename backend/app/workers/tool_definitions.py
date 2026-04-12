"""
Tool Definitions — Anthropic-format JSON schemas for autonomous agent tools.

Each tool is a dict with name, description, and input_schema (JSON Schema).
get_tools_for_role() returns the subset of tools an agent is allowed to use
based on its RoleLevel: CEO/Admin sees all, supervisors can't create departments,
regular agents can only query.

These definitions are passed to Claude's `tools` parameter — Claude decides
which to call based on the task context.
"""

from app.agents.models import RoleLevel

# ── Tool schemas (Anthropic tool_use format) ──

CREATE_DEPARTMENT = {
    "name": "create_department",
    "description": (
        "Crea un nuevo departamento en la organización. "
        "Úsalo cuando detectes que falta un área funcional necesaria "
        "para completar una tarea o cumplir un objetivo estratégico."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Nombre del departamento (ej: 'Finanzas', 'Recursos Humanos')",
            },
            "description": {
                "type": "string",
                "description": "Descripción breve del propósito y responsabilidades del departamento",
            },
        },
        "required": ["name", "description"],
    },
}

CREATE_AGENT = {
    "name": "create_agent",
    "description": (
        "Crea un nuevo agente interno en un departamento. "
        "Úsalo cuando necesites un especialista que no existe aún "
        "para completar una tarea específica."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name": {
                "type": "string",
                "description": "Nombre del agente (ej: 'Analista de Presupuestos')",
            },
            "description": {
                "type": "string",
                "description": "Descripción del rol y responsabilidades del agente",
            },
            "department_slug": {
                "type": "string",
                "description": "Slug del departamento donde se creará el agente",
            },
            "role": {
                "type": "string",
                "enum": ["agent", "supervisor"],
                "description": "Nivel de rol: 'agent' para especialistas, 'supervisor' para jefes de equipo",
            },
            "capabilities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Lista de capacidades del agente (ej: ['análisis financiero', 'proyecciones'])",
            },
        },
        "required": ["name", "description", "department_slug", "capabilities"],
    },
}

GENERATE_PROMPT = {
    "name": "generate_prompt",
    "description": (
        "Genera un system prompt especializado para un agente existente. "
        "Úsalo después de crear un agente para configurar su personalidad, "
        "conocimientos y estilo de trabajo."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_slug": {
                "type": "string",
                "description": "Slug del agente que recibirá el system prompt",
            },
            "role_description": {
                "type": "string",
                "description": "Descripción detallada del rol para generar un prompt adecuado",
            },
            "capabilities": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Capacidades que el prompt debe reflejar",
            },
        },
        "required": ["agent_slug", "role_description", "capabilities"],
    },
}

ASSIGN_TASK = {
    "name": "assign_task",
    "description": (
        "Asigna una nueva tarea a un agente específico. "
        "Úsalo para delegar trabajo a agentes existentes o recién creados."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "agent_slug": {
                "type": "string",
                "description": "Slug del agente que ejecutará la tarea",
            },
            "title": {
                "type": "string",
                "description": "Título conciso de la tarea",
            },
            "description": {
                "type": "string",
                "description": "Instrucciones detalladas para el agente",
            },
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high", "critical"],
                "description": "Prioridad de la tarea (default: medium)",
            },
        },
        "required": ["agent_slug", "title", "description"],
    },
}

LIST_DEPARTMENTS = {
    "name": "list_departments",
    "description": (
        "Lista todos los departamentos de la organización con su conteo de agentes. "
        "Úsalo para entender la estructura actual antes de crear departamentos o agentes."
    ),
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}

LIST_DEPARTMENT_AGENTS = {
    "name": "list_department_agents",
    "description": (
        "Lista los agentes de un departamento específico con sus capacidades y estado. "
        "Úsalo para saber quién está disponible antes de asignar tareas."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "department_slug": {
                "type": "string",
                "description": "Slug del departamento a consultar",
            },
        },
        "required": ["department_slug"],
    },
}

# ── All tools indexed by name ──

ALL_TOOLS: dict[str, dict] = {
    "create_department": CREATE_DEPARTMENT,
    "create_agent": CREATE_AGENT,
    "generate_prompt": GENERATE_PROMPT,
    "assign_task": ASSIGN_TASK,
    "list_departments": LIST_DEPARTMENTS,
    "list_department_agents": LIST_DEPARTMENT_AGENTS,
}

# ── Permission matrix: which roles can use which tools ──
# CEO/Admin: everything
# Supervisor: create agents in own dept, generate prompts, assign tasks, query
# Agent: read-only queries

_ROLE_PERMISSIONS: dict[RoleLevel, set[str]] = {
    RoleLevel.ADMIN: set(ALL_TOOLS.keys()),
    RoleLevel.MANAGER: set(ALL_TOOLS.keys()),
    RoleLevel.SUPERVISOR: {
        "create_agent",
        "generate_prompt",
        "assign_task",
        "list_departments",
        "list_department_agents",
    },
    RoleLevel.AGENT: {
        "list_departments",
        "list_department_agents",
    },
}


def get_tools_for_role(role_level: RoleLevel) -> list[dict]:
    """
    Return Anthropic-format tool definitions filtered by the agent's role level.

    CEO/Admin gets all tools. Supervisors can't create departments.
    Regular agents can only query org structure.
    """
    allowed_names = _ROLE_PERMISSIONS.get(role_level, set())
    return [ALL_TOOLS[name] for name in allowed_names if name in ALL_TOOLS]


def get_tool_names_for_role(role_level: RoleLevel) -> list[str]:
    """Return just the tool names allowed for a given role (for seeding AgentDefinition.tools)."""
    return sorted(_ROLE_PERMISSIONS.get(role_level, set()))
