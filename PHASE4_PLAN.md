# Phase 4: Autonomous Agent Management — Implementation Plan

## Context

El producto CRM Agents está demo-ready con 3 fases completadas. El siguiente paso es hacer que los agentes se auto-gestionen como una empresa real: el CEO detecta que falta un departamento y lo crea, los supervisores detectan que necesitan un especialista y lo crean, el Prompt Engineer genera system prompts especializados, y el sistema sugiere dar de baja agentes que no se usan.

**Problema concreto:** Hoy un usuario pide "crear un post de LinkedIn" pero falta un diseñador de imágenes. El Director de Contenido debería poder crear ese agente, pedir al Prompt Engineer que le cree su system prompt, y asignarle la tarea — sin intervención humana.

## Decisión arquitectónica: Claude `tool_use`

Usar el mismo patrón que ya funciona en `supervisor_delegator.py` (línea 302): pasar `tools=[...]` a Claude y procesar bloques `tool_use` en la respuesta. Cada herramienta es una función Python que ejecuta la acción (crear departamento, crear agente, etc.) y retorna el resultado a Claude para que continúe razonando.

**Por qué no task-chaining:** Con tool_use todo ocurre en una conversación — Claude razona, usa una herramienta, ve el resultado, y decide si necesita otra. Con task-chaining habría múltiples llamadas a Claude, latencia, y complejidad de recovery si una falla.

---

## Sub-Phase 4A: Tool Infrastructure (Foundation)

**Meta:** Generalizar el executor para que cualquier agente pueda usar tools, no solo supervisores.

### Archivos a crear

**`backend/app/workers/tool_registry.py`**
- Registry `dict[str, ToolHandler]` que mapea nombre → función async
- `ToolContext` dataclass con `db`, `org_id`, `calling_agent_id`, `calling_agent_role`
- `execute_tool(name, input, context) -> dict` que busca el handler y lo ejecuta
- Decorador `@register_tool("nombre")` para registrar handlers

**`backend/app/workers/tool_definitions.py`**
- JSON schemas de cada tool (formato Anthropic `tools` param)
- Función `get_tools_for_role(role_level: RoleLevel) -> list[dict]` que retorna las tools permitidas según el rol

### Archivos a modificar

**`backend/app/workers/agent_executor.py`** — `_execute_internal()`
- Si `definition.tools` no está vacío, usar un tool loop:
  1. Llamar a Claude con `tools=definition.tools`
  2. Si response tiene bloque `tool_use` → ejecutar via `tool_registry.execute_tool()`
  3. Append `tool_result` a messages, llamar a Claude de nuevo
  4. Repetir hasta `stop_reason="end_turn"`
  5. Extraer texto final
- El flujo actual (sin tools) queda igual — solo activa si `definition.tools` tiene contenido
- Reutilizar `_call_claude_with_retry()` que ya existe

### Seed / Config

**`backend/seed.py`** — Actualizar el CEO (o crear un agente CEO explícito) con tools en su `AgentDefinition.tools`. Los supervisores de departamento reciben subset de tools.

---

## Sub-Phase 4B: Tool Handlers (Core Feature)

**Meta:** Implementar las herramientas que permiten crear departamentos, agentes, y system prompts.

### Archivos a crear

**`backend/app/workers/tools/__init__.py`**

**`backend/app/workers/tools/create_department.py`**
- Input: `{"name", "description"}`
- Reutiliza: `DepartmentService.create_department()` (`departments/service.py`)
- Output: `{"success", "department_id", "slug"}`
- Valida: max 20 departamentos por org (previene runaway)
- Log: `ActivityLog` action `autonomous_department_created`
- SSE: `department.created`

**`backend/app/workers/tools/create_agent.py`**
- Input: `{"name", "description", "department_slug", "role", "capabilities"}`
- Reutiliza: `AgentService.create_internal_agent()` (`agents/service.py` ~línea 160+)
- Output: `{"success", "agent_id", "slug"}`
- Valida: max 15 agentes por departamento, supervisors solo crean en su depto
- Guarda `created_by_agent_id` (nuevo campo, ver 4C)
- Log + SSE

**`backend/app/workers/tools/generate_prompt.py`**
- Input: `{"agent_slug", "role_description", "capabilities"}`
- Hace una llamada separada a Claude API con meta-prompt para generar system prompt
- Reutiliza: `PromptService.create_version()` (`prompts/service.py`)
- Actualiza `AgentDefinition.system_prompt` directamente
- Output: `{"success", "prompt_preview"}`

**`backend/app/workers/tools/assign_task.py`**
- Input: `{"agent_slug", "title", "description", "priority"}`
- Reutiliza: `TaskService.create_task()` (`tasks/service.py`)
- Seta `Task.created_by` al agente que llama (campo existe pero siempre es NULL hoy)
- Output: `{"success", "task_id"}`

**`backend/app/workers/tools/query_org.py`**
- `list_departments`: retorna departamentos con conteo de agentes
- `list_department_agents`: retorna agentes de un depto con capabilities y status
- Read-only, usan repos existentes

### Scope / Permissions por rol

| Tool | CEO/Admin | Supervisor | Agent |
|------|-----------|------------|-------|
| create_department | Si | No | No |
| create_agent | Si | Solo su depto | No |
| generate_prompt | Si | Si | No |
| assign_task | Si | Si | No |
| list_departments | Si | Si | Si |
| list_department_agents | Si | Si (su depto) | No |

---

## Sub-Phase 4C: Agent Lifecycle Management

**Meta:** Detectar agentes sin uso y sugerir al humano darlos de baja.

### Alembic migration (nuevo archivo)

Tabla `agents` — agregar columnas:
- `last_task_completed_at: DateTime, nullable` — se actualiza al completar tarea
- `total_tasks_completed: Integer, default=0` — counter
- `created_by_agent_id: UUID, FK agents.id, nullable` — qué agente lo creó
- `creation_reason: Text, nullable` — contexto de por qué se creó

Tabla nueva `notifications`:
- `id, organization_id, agent_id (nullable), title, body, notification_type (enum), is_read, action_url, created_at`

### Archivos a crear

**`backend/app/workers/lifecycle_monitor.py`**
- Background worker nuevo (agregar en `main.py` lifespan junto a los otros 3)
- Corre cada 24h
- Detecta agentes idle: `last_task_completed_at < now - 7 days` O `created_at < now - 3 days AND total_tasks_completed = 0`
- Atención extra a `created_by_agent_id IS NOT NULL` (creados autónomamente)
- Crea notificación + emite SSE `agent.idle_detected`
- **Nunca desactiva automáticamente** — solo sugiere al humano

**`backend/app/notifications/`** (módulo nuevo, patrón estándar)
- `models.py` — Notification model
- `repository.py` — queries scoped por org
- `service.py` — create, list_unread, mark_read, execute_action
- `router.py` — GET /notifications/, PATCH /{id}/read, POST /{id}/action
- `schemas.py` — NotificationResponse, etc.

### Archivos a modificar

**`backend/app/workers/agent_executor.py`** — después de task completed (línea 340):
```python
agent.last_task_completed_at = datetime.utcnow()
agent.total_tasks_completed = (agent.total_tasks_completed or 0) + 1
```

**`backend/app/agents/models.py`** — agregar los 4 campos nuevos al modelo Agent

**`backend/app/main.py`** — registrar lifecycle_monitor worker + notifications router

---

## Sub-Phase 4D: Frontend

**Meta:** Que el usuario vea las acciones autónomas y gestione el lifecycle.

### Archivos a crear

**`frontend/src/features/notifications/NotificationPanel.tsx`**
- Dropdown desde el icono de campana (ya existe en el header)
- Badge con count de unread
- Cada notificación tiene botones de acción ("Desactivar" / "Mantener")
- Consume `GET /api/v1/notifications/`

**`frontend/src/api/notifications.ts`**
- Client API para el módulo de notificaciones

**`frontend/src/features/agents/AgentLifecycleCard.tsx`**
- En la página de detalle del agente, mostrar:
  - Quién lo creó (humano o agente)
  - Razón de creación
  - Última tarea completada, total de tareas
  - Días idle
  - Botón "Desactivar" si idle

### Archivos a modificar

**`frontend/src/features/agents/AgentDetailPage.tsx`** — integrar AgentLifecycleCard
**`frontend/src/components/layout/`** — conectar NotificationPanel al header

---

## Protecciones contra runaway

1. **Hard limits:** max 20 deptos/org, max 15 agentes/depto (en tool handlers)
2. **Rate limit:** max 3 creaciones de agente por hora por agente (en tool_registry)
3. **Toda creación autónoma genera notificación** al humano
4. **Lifecycle monitor** flaggea agentes autónomos con <2 tareas después de 3 días
5. **Cost tracking:** tokens usados en operaciones autónomas se logean en ActivityLog

---

## Orden de implementación

1. **4A** — Tool infrastructure + tool loop en executor
2. **4B** — Tool handlers + setup CEO/Prompt Engineer
3. **4C** — Migration + lifecycle monitor + notificaciones backend
4. **4D** — Frontend notifications + lifecycle UI

## Verificación end-to-end

1. Crear tarea para CEO: "Necesitamos un departamento de Finanzas con un analista de presupuestos para planear la inversión en publicidad"
2. Verificar que CEO usa `create_department` → `create_agent` → `generate_prompt` → `assign_task`
3. Verificar ActivityLog muestra cada paso
4. Verificar SSE events llegan al frontend
5. Esperar lifecycle monitor y verificar notificación de idle agents
6. Verificar que los hard limits funcionan (intentar crear >20 departamentos)

## Archivos críticos existentes a reutilizar

- `backend/app/workers/supervisor_delegator.py` — patrón tool_use completo (líneas 44-87 tool def, 295-304 llamada con tools)
- `backend/app/workers/agent_executor.py` — `_call_claude_with_retry()`, `_log_activity()`, `_emit()`
- `backend/app/agents/service.py:create_internal_agent()` — crea Agent + AgentDefinition
- `backend/app/departments/service.py:create_department()` — crea Department con slug
- `backend/app/prompts/service.py:create_version()` — crea PromptVersion
- `backend/app/tasks/service.py:create_task()` — crea Task con auto-assign
- `backend/app/tasks/router.py:116` — routing por role (supervisor vs agent)
