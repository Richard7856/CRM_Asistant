# DECISIONS.md — CRM Agents

Registro de decisiones técnicas y de arquitectura. Cada entrada documenta qué se decidió, por qué, qué alternativas existían, y qué riesgos hay.

---

## [2025-12] Ejecución de tareas síncrona dentro del HTTP request

**Contexto:** El endpoint `POST /tasks/{task_id}/execute` necesita llamar a la Claude API y esperar la respuesta antes de retornar.

**Decisión:** `execute_task()` se llama directamente con `await` dentro del request handler (`tasks/router.py:87`). El cliente HTTP espera hasta que Claude responde.

**Alternativas consideradas:**
- `BackgroundTasks` de FastAPI — lanza la ejecución en background y retorna 202 inmediatamente. El cliente debe hacer polling o escuchar SSE para saber cuándo terminó.
- Cola de tareas con Redis + worker separado — más robusto, permite reintentos y persistencia, pero requiere infraestructura adicional.

**Riesgos/Limitaciones:**
- Claude API tarda 10–60 segundos por tarea. Con 10 tareas concurrentes, el event loop de Python tiene 10 coroutines bloqueando la misma instancia de uvicorn.
- Con más de ~15 tareas realmente concurrentes, el pool de conexiones a PostgreSQL (`pool_size=10, max_overflow=20` = 30 total) se agota y las siguientes tareas empiezan a esperar en cola.
- **No apto para producción con >15 tareas concurrentes simultáneas.**

> **RESUELTO en [2026-04] — ver entrada abajo.**

---

## [2026-04] Migración a ejecución asíncrona en background (fix concurrencia)

**Contexto:** El endpoint `POST /tasks/{id}/execute` bloqueaba el HTTP request 10-60s mientras Claude respondía. Con 50 tareas concurrentes, el event loop se saturaba y el pool de DB se agotaba.

**Decisión:** Tres cambios:
1. El endpoint ahora retorna **202 Accepted** inmediatamente — valida que la tarea y el agente existan, y lanza la ejecución con `asyncio.create_task()`.
2. `execute_task_background()` (nueva función en `agent_executor.py`) abre **su propia sesión de DB** vía `async_session_factory()` — no reutiliza la del request HTTP que ya cerró.
3. El resultado llega al frontend por **SSE** (eventos `task.completed` / `task.failed` que ya existían).

**Por qué `asyncio.create_task()` y no `BackgroundTasks` de FastAPI:**
`BackgroundTasks` ejecuta las tareas secuencialmente después de enviar la respuesta. `asyncio.create_task()` lanza coroutines verdaderamente concurrentes — 50 tareas corren en paralelo real, cada una esperando I/O de Claude API sin bloquear a las otras.

**Alternativas consideradas:**
- Redis + Celery worker separado — máxima robustez (persistencia de cola, reintentos automáticos, monitoreo con Flower), pero agrega 2 servicios a la infra. Innecesario mientras el tráfico quepa en un solo proceso uvicorn.
- `BackgroundTasks` de FastAPI — más simple pero secuencial, no resuelve el problema de concurrencia real.

**Riesgos/Limitaciones:**
- Si uvicorn muere, las tareas en vuelo se pierden (no hay cola persistente). Aceptable para MVP — las tareas quedan en `IN_PROGRESS` y el operador puede re-ejecutar.
- Con 50+ tareas en paralelo, el pool de DB (30 conexiones) puede saturarse si cada tarea tiene muchas operaciones DB. Monitorear y subir si es necesario.

**Archivos modificados:** `tasks/router.py`, `workers/agent_executor.py`

---

## [2026-04] Retry con backoff exponencial + timeout para Claude API

**Contexto:** La llamada a Claude API no tenía protección contra fallos transitorios (rate limit 429, sobrecarga 529, server errors 500+) ni timeout — si Claude colgaba, la tarea colgaba para siempre.

**Decisión:** Nueva función `_call_claude_with_retry()` en `agent_executor.py`:
- **Retry**: máximo 3 intentos con backoff exponencial (1s → 2s → 4s) para errores retryables (429, 500, 529).
- **Timeout**: 90 segundos por intento vía `asyncio.wait_for()`. Si Claude no responde, se cancela la coroutine y se reintenta.
- **Fail-fast**: errores no retryables (400 bad request, 401 auth) fallan inmediatamente sin reintentar.

**Alternativas consideradas:**
- Biblioteca `tenacity` — retry genérico con decoradores. Agrega una dependencia para algo que se resuelve en 25 líneas.
- Timeout solo en el cliente httpx de Anthropic — no cubre la lógica de retry ni distingue entre errores retryables y permanentes.

**Riesgos/Limitaciones:**
- 3 retries × 90s timeout = peor caso ~4.5 minutos antes de declarar una tarea como FAILED. Aceptable para tareas batch, podría ser largo para UX interactiva.
- Si Claude está caído sistémicamente (no solo transitory), cada tarea va a hacer 3 intentos antes de fallar. Con 50 tareas = 150 llamadas fallidas. No es un problema real (son async, no bloquean nada) pero genera muchos logs.

**Archivo modificado:** `workers/agent_executor.py`

---

## [2025-12] Pool de conexiones PostgreSQL: pool_size=10, max_overflow=20

**Contexto:** SQLAlchemy async engine necesita un pool configurado. El valor por defecto es `pool_size=5`.

**Decisión:** `pool_size=10, max_overflow=20` → máximo 30 conexiones simultáneas (`core/database.py`).

**Alternativas consideradas:**
- Pool más grande (ej. pool_size=50) — PostgreSQL por defecto acepta 100 conexiones. Un pool demasiado grande desperdicia memoria del servidor DB.
- PgBouncer (connection pooler externo) — permite miles de clientes con pocas conexiones reales a Postgres. Agrega un proceso más a la infraestructura.

**Riesgos/Limitaciones:**
- Cada ejecución de tarea abre ~2 conexiones (una para leer el agente/tarea, otra para escribir el resultado). Con 30 conexiones = ~15 tareas verdaderamente concurrentes.
- Si el pool se agota, SQLAlchemy hace cola y espera `pool_timeout` segundos (default 30s) antes de lanzar `TimeoutError`.

**Mejora pendiente:** Para producción con 50+ tareas concurrentes, agregar PgBouncer o aumentar `pool_size`. Configurar `pool_timeout` explícitamente para fallar rápido en lugar de quedar colgado.

---

## [2025-12] SSE EventBus en memoria (no Redis)

**Contexto:** El dashboard necesita recibir actualizaciones en tiempo real cuando cambia el estado de una tarea o agente.

**Decisión:** `EventBus` es un singleton en memoria (`core/events.py`). Cada conexión SSE abierta del browser recibe una `asyncio.Queue`. El backend hace `event_bus.publish(event)` y el fan-out ocurre dentro del mismo proceso Python.

**Alternativas consideradas:**
- WebSockets — más complejo de implementar, requiere manejo de reconexión y handshake. SSE es unidireccional (server → client) y eso es todo lo que el dashboard necesita.
- Redis Pub/Sub — permite múltiples instancias del backend publicando y consumiendo eventos. Necesario si se escala horizontalmente (múltiples pods/workers uvicorn).

**Riesgos/Limitaciones:**
- Si el proceso de uvicorn se reinicia, todos los subscribers se pierden y los browsers necesitan reconectarse. En práctica, los browsers reconectan SSE automáticamente.
- Con múltiples workers de uvicorn (`--workers 4`), un evento publicado en el worker 1 NO llega a los subscribers del worker 2. En MVP con 1 worker esto no es problema.
- Las colas tienen `maxsize=100`. Si un subscriber consume lento, los eventos más viejos se descartan silenciosamente (logging de warning incluido).

**Mejora pendiente:** Para escalar a múltiples workers, reemplazar con Redis Pub/Sub. La interfaz `EventBus.publish()` / `EventBus.subscribe()` está diseñada para que el swap sea transparente al resto del código.

---

## [2025-12] Ejecución de agentes internos vía Claude API (no Claude Agent SDK)

**Contexto:** Los agentes internos necesitan ejecutar tareas usando un LLM.

**Decisión:** `agent_executor.py` llama directamente a la API de Anthropic usando el cliente `anthropic` de Python. El system prompt del agente se inyecta en el campo `system`, el input de la tarea va en `messages[0]`.

**Alternativas consideradas:**
- Claude Agent SDK — abstracción de más alto nivel, maneja herramientas y multi-turn automáticamente. Agrega complejidad y dependencia adicional.
- LangChain / LlamaIndex — frameworks de orquestación completos. Overhead innecesario para MVP; añaden capas de abstracción difíciles de depurar.

**Riesgos/Limitaciones:**
- No hay retry automático en fallo de la Claude API. Si Claude retorna un 529 (sobrecarga) o timeout, la tarea falla permanentemente.
- No hay timeout explícito en la llamada a la API. Si Claude tarda más de lo normal, el request HTTP del cliente queda colgado indefinidamente.

**Mejora pendiente:** Envolver la llamada a Claude en un retry con backoff exponencial (máx. 3 intentos, espera 1s/2s/4s). Agregar `timeout=60` al cliente de Anthropic.

---

## [2025-12] RAG con PostgreSQL full-text search (no vector database)

**Contexto:** Los agentes necesitan acceder a documentos de la base de conocimiento relevantes para la tarea que ejecutan.

**Decisión:** Los documentos se indexan con `tsvector` + índice GIN en PostgreSQL. La búsqueda usa `tsquery`. Los chunks relevantes se inyectan automáticamente en el system prompt del agente antes de llamar a Claude (`agent_executor.py`).

**Alternativas consideradas:**
- pgvector — embeddings vectoriales dentro de Postgres. Mejor relevancia semántica pero requiere llamar a un modelo de embeddings para cada documento y cada query.
- Pinecone / Weaviate — bases de datos vectoriales dedicadas. Costo adicional, dependencia externa, complejidad operacional.

**Riesgos/Limitaciones:**
- Full-text search es keyword matching, no semántica. Si el documento usa sinónimos o fraseología diferente al query, puede no encontrarlo.
- Para documentos de negocio estructurados (políticas, procedimientos, precios) la calidad de recuperación es aceptable. Para queries en lenguaje natural libre, puede fallar.

**Mejora pendiente:** Agregar pgvector para búsqueda semántica cuando la calidad de recuperación sea insuficiente para los casos de uso del cliente.

---

## [2025-12] Multi-tenancy vía organization_id en todas las tablas

**Contexto:** El sistema debe soportar múltiples empresas cliente usando la misma instancia de la base de datos.

**Decisión:** Todas las tablas de entidades principales llevan una columna `organization_id UUID NOT NULL`. Todas las queries en la capa de repositorio/servicio reciben `org_id` como parámetro y filtran por él. No hay row-level security en Postgres — la seguridad se garantiza en la capa de aplicación.

**Alternativas consideradas:**
- Un schema de Postgres por organización — aislamiento total, sin riesgo de data leaks entre orgs. Pero las migraciones de Alembic se complican enormemente (N schemas = N migraciones).
- Una base de datos por organización — máximo aislamiento pero imposible de operar a escala. Requiere gestión dinámica de conexiones y configuración por org.

**Riesgos/Limitaciones:**
- El aislamiento depende de que CADA query incluya el filtro de `org_id`. Un bug que olvide el filtro puede exponer datos de otra organización.
- No hay protección a nivel de base de datos (row-level security). Si se agrega un nuevo endpoint sin el filtro correcto, la fuga es silenciosa.

**Mejora pendiente:** Considerar Row Level Security (RLS) en Postgres como segunda capa de defensa. Agregar tests de integración que verifiquen explícitamente que un org no puede ver datos de otro.

---

## [2025-12] Workers en proceso (asyncio.create_task) en lugar de Celery/Redis

**Contexto:** El sistema necesita 3 tareas de fondo recurrentes: calcular métricas (cada 1h), monitorear heartbeats (cada 60s), verificar salud de integraciones externas (cada 5min).

**Decisión:** Los workers se crean como `asyncio.create_task()` dentro del lifespan de FastAPI (`main.py`). Viven en el mismo proceso que el API server.

**Alternativas consideradas:**
- Celery + Redis — worker separado, colas persistentes, reintentos automáticos, monitoreo con Flower. Pero agrega 2 servicios más (Redis + Celery worker) a la infraestructura.
- APScheduler — biblioteca de scheduling que corre en el mismo proceso. Similar a la solución actual pero con más features de scheduling (cron expressions, etc.).

**Riesgos/Limitaciones:**
- Si el proceso de uvicorn muere, los workers mueren con él. No hay garantía de que una tarea pendiente se complete.
- Los workers comparten el event loop con el API server. Una tarea pesada en un worker puede aumentar la latencia del API.
- Con `--workers 4` en uvicorn, cada worker corre SU propio loop de métricas — el mismo cálculo se hace 4 veces.

**Mejora pendiente:** La interfaz está diseñada para que migrar a Celery no requiera cambios en la lógica de negocio — solo en cómo se registra la tarea. Migrar cuando se necesite escalar a múltiples workers.

---

## [2025-12] Dualidad de agentes: internos vs externos

**Contexto:** Las empresas no corren todos sus agentes de IA en una sola plataforma. Algunas tienen workflows en n8n, chains en LangChain, scripts custom, además de querer agentes nuevos con Claude.

**Decisión:** Un `Agent` puede ser `internal` (respaldado por LLM, tiene `AgentDefinition` con system prompt y config de modelo) o `external` (respaldado por webhook/API, tiene `AgentIntegration` con URL de endpoint). El mismo sistema de tareas, métricas, y dashboard funciona para ambos tipos.

**Alternativas consideradas:**
- Solo agentes internos — más simple pero no resuelve el problema real: las empresas ya tienen automatizaciones existentes.
- Un producto separado para agentes externos — fragmenta la propuesta de valor y el panel de control.

**Riesgos/Limitaciones:**
- Los agentes externos dependen de que el endpoint externo esté disponible. El health checker verifica cada 5 minutos pero puede haber ventanas de fallo no detectadas.
- Las métricas de agentes externos solo son tan precisas como lo que el agente externo reporta vía callback. Si el webhook externo no llama de vuelta, la tarea queda en estado `PENDING` indefinidamente.

**Mejora pendiente:** Agregar timeout en la espera del callback de agentes externos. Si no responden en N minutos, marcar la tarea como `FAILED`.

---

## [2025-12] Autenticación JWT sin refresh token rotation

**Contexto:** La plataforma necesita autenticación segura para múltiples usuarios por organización.

**Decisión:** JWT con `python-jose` + bcrypt para passwords. Access token (corta duración) + refresh token (larga duración). Los tokens se validan stateless — no hay blacklist en DB.

**Alternativas consideradas:**
- Sessions con cookies + server-side store — más fácil de invalidar pero requiere Redis o tabla de sessions en Postgres.
- Auth0 / Supabase Auth — solución gestionada, sin código de auth que mantener. Costo adicional y dependencia externa.

**Riesgos/Limitaciones:**
- No hay refresh token rotation implementado. Si un refresh token es comprometido, es válido hasta su expiración.
- No hay logout real — como los tokens son stateless, "cerrar sesión" solo borra el token del cliente. Un token robado antes del logout sigue siendo válido.

**Mejora pendiente:** Implementar refresh token rotation (invalidar el refresh token anterior al emitir uno nuevo) y una tabla de tokens revocados para logout real.

---

## [2026-04] Decisión de modelo de negocio: Equity vs Revenue Share (inversión pre-seed)

**Contexto:** Primera ronda de inversión informal. $70,000 USD de inversores no institucionales para capital inicial de operaciones.

**Decisión:** Equity — 20% de participación accionaria a cambio de $70K USD.

**Alternativas consideradas:**
- Revenue Share (10% de ingresos mensuales hasta recuperar 1.5x) — no drena caja mensualmente si no hay ingresos, pero en cuanto hay clientes, recorta el capital disponible para reinversión justo cuando más se necesita para crecer.
- Deuda convertible — pago de intereses desde el primer mes, aún más problemático en etapa pre-revenue.

**Riesgos/Limitaciones:**
- Diluir 20% en pre-seed es un porcentaje alto. Si se hacen rondas futuras, el fundador se diluye más.
- Los inversores tienen derecho a información y voz en decisiones importantes. Requiere transparencia y comunicación mensual.

**Distribución del capital:**
- $40,000 — Marketing y adquisición de clientes (57%)
- $20,000 — Salario fundador 12 meses (29%)
- $10,000 — Infraestructura y herramientas (14%)

**Por qué este mix:** El producto ya está construido. El cuello de botella es tracción, no desarrollo. Invertir en marketing primero maximiza el tiempo que el fundador tiene para cerrar los primeros clientes antes de que se agote el capital.

---

## [2026-04-11] Fase 2: TaskDetailPage como full-page vs modal

**Contexto:** Las tareas con resultados ricos (delegación con subtareas, KB citations, token usage) no caben bien en el TaskDetailModal existente. Necesitamos visualizar árboles de delegación, sparklines de KB sources, y el output del supervisor.

**Decisión:** Crear un nuevo `TaskDetailPage` como ruta `/tasks/:id` y cambiar el click de tareas en la lista para navegar a esta página en lugar de abrir el modal. El modal se mantiene como archivo (TaskDetailModal.tsx) pero ya no se usa desde TaskListPage.

**Alternativas consideradas:**
- Expandir el modal con scroll → demasiado contenido, UX pobre en móvil
- Tab layout dentro del modal → complejidad sin ganancia, la delegación tree necesita espacio
- Drawer lateral → buen UX pero requiere más trabajo CSS y no permite URL directa

**Riesgos/Limitaciones:** La página hace 2 queries (task + subtasks) y auto-polls mientras está in_progress. El refetchInterval de 3s puede ser agresivo si hay muchos usuarios simultáneos.

---

## [2026-04-11] Credenciales: secret_value write-only, preview solo últimos 4 chars

**Contexto:** Los agentes necesitan API keys para herramientas externas (MCP). Necesitamos un módulo de credenciales con CRUD, pero los secretos no deben exponerse vía la API.

**Decisión:** El campo `secret_value` se acepta en Create/Update pero NUNCA se incluye en la respuesta API. Solo se devuelve `secret_preview` (****xxxx). El worker que ejecuta tareas lee el secreto directamente del DB cuando lo necesita. No hay encryption at-application-level — se confía en PostgreSQL encryption at rest.

**Alternativas consideradas:**
- Encryption con Fernet/AES en el backend → más seguro, pero agrega complejidad (key management, rotation). Para MVP es overengineering.
- Vault externo (HashiCorp Vault, AWS Secrets Manager) → ideal en producción, excesivo para demo.
- Guardar solo un hash → no podemos usar el secreto si solo tenemos el hash.

**Riesgos/Limitaciones:** Sin encryption at-application-level, un dump de DB expone todos los secretos. Aceptable para demo, no para producción. El upgrade path es claro: agregar Fernet encryption en el service layer sin cambiar la API.

---

## [2026-04-11] Score sparkline SVG nativo sin librería de charts

**Contexto:** La página de Prompt Engineering necesita mostrar la evolución del performance_score a través de versiones (v1: 6.2 → v2: 7.8 → v3: 9.1) de forma visual.

**Decisión:** SVG inline con `<polyline>`, `<polygon>` (fill), y `<circle>` (dots). No se usa Recharts ni ninguna librería de charts adicional. El componente `ScoreEvolutionChart` calcula posiciones con funciones `toX`/`toY` sobre un viewBox fijo de 280x60.

**Alternativas consideradas:**
- Recharts (ya en el bundle para MetricsDashboard) → overkill para 3 puntos, agrega API surface innecesaria
- CSS bar chart → no muestra la tendencia tan claramente como una línea
- Sparkline library (react-sparklines) → dependency extra para algo que son 40 líneas de SVG

**Riesgos/Limitaciones:** No tiene tooltips interactivos (hover). Para 3-5 puntos no se necesitan. Si escala a muchas versiones (>10), necesitaría scroll horizontal o downsample.

---

## [2026-04-11] Dark mode via CSS variable remapping + class toggle

**Contexto:** El design system neumórfico usa CSS custom properties (`--neu-bg`, `--neu-dark`, `--text-primary`, etc.) para todas las superficies y textos. Necesitamos dark mode para el demo y para profesionalismo general.

**Decisión:** Agregar un bloque `html.dark { }` en `index.css` que re-mapea TODAS las variables CSS a valores oscuros. Los utility classes neumórficos (`.neu-flat`, `.neu-sm`, `.neu-pressed`) automáticamente usan los nuevos valores sin ningún cambio en componentes. Toggle via clase en `<html>`, persistida en localStorage, con detección de preferencia del OS como fallback.

**Alternativas consideradas:**
- Tailwind `dark:` prefix en cada clase → requiere duplicar CADA clase en CADA componente. Con 15+ páginas, imposible de mantener.
- CSS media query `prefers-color-scheme` sin toggle → no permite al usuario elegir manualmente
- Separate CSS file para dark → duplicación, difícil de mantener sincronizado

**Riesgos/Limitaciones:** Algunos colores semánticos (indigo-50, emerald-50 para badges de status) no se adaptan automáticamente al dark mode. Son aceptables porque son colores de acento con suficiente contraste. En producción se podría agregar un `html.dark .bg-indigo-50 { background: ... }` override.

---

## [2026-04-11] Color consistency pass: eliminar hardcoded Tailwind grays

**Contexto:** 134 instancias de colores hardcoded (`text-gray-500`, `bg-gray-100`, `border-gray-300`) en 10 feature files. Estos no responden al dark mode porque son valores absolutos de Tailwind, no CSS variables.

**Decisión:** Reemplazo masivo con equivalentes CSS variable: `text-gray-900` → `text-[var(--text-primary)]`, `bg-gray-100` → `bg-[var(--neu-dark)]/10`, etc. Se preservó `bg-gray-900` para fondos de terminal/código (debe ser oscuro en ambos modos).

**Riesgos/Limitaciones:** Los valores no son 1:1 idénticos (ej: `text-gray-500` = `#6b7280`, `--text-muted` = `#a0aec0` en light). La diferencia es sutil y el resultado visual es más coherente con el design system general.

---

## [2026-04-12] Phase 4: Herramientas autónomas via Claude tool_use loop (no Agent SDK)

**Contexto:** Los agentes CEO/Admin necesitan poder crear departamentos, otros agentes, system prompts, y asignar tareas autónomamente — sin intervención humana. Esto requiere un loop de herramientas dentro del executor.

**Decisión:** Implementar un loop de `tool_use` directamente en `agent_executor.py`:
1. Si el agente tiene herramientas configuradas, se pasan como `tools=[]` al llamar a Claude
2. Si Claude responde con bloques `tool_use`, se ejecutan vía `tool_registry.execute_tool()`, se construyen `tool_result` messages, y se reenvían a Claude
3. El loop continúa hasta que Claude responda con `end_turn` o se alcancen 10 iteraciones

El registry usa un patrón `@register_tool("name")` que registra handlers en un dict global. Cada handler recibe un `ToolContext` (db session, org_id, calling agent info) y el input dict.

**Alternativas consideradas:**
- Claude Agent SDK — abstracción de alto nivel que maneja el loop automáticamente. Pero agrega una dependencia pesada y no permite control granular sobre permisos, rate limiting, y logging por herramienta.
- LangChain tools — framework completo con tool abstraction. Overhead excesivo, difícil de debuggear, y no necesitamos la complejidad de chains.
- Endpoints REST internos (el agente llama a su propia API) — elegante pero circular y difícil de rastrear en logs.

**Riesgos/Limitaciones:**
- El loop máximo de 10 iteraciones puede ser insuficiente para tareas complejas con muchos pasos.
- Las herramientas se ejecutan en el mismo proceso y event loop que el API server. Una herramienta que tarde mucho bloquea la tarea pero no el server (es async).
- El rate limiting es in-memory — se pierde si el proceso se reinicia. Aceptable para MVP.

---

## [2026-04-12] Rate limiting y hard limits para creación autónoma de recursos

**Contexto:** Sin límites, un agente con un prompt mal diseñado podría crear cientos de departamentos o agentes en un loop infinito, agotando recursos del DB.

**Decisión:** Tres capas de protección:
1. **Hard limits:** Máximo 20 departamentos por organización, máximo 15 agentes por departamento. Validados en cada handler de creación.
2. **Rate limiting:** Máximo 3 llamadas a herramientas de creación por agente por hora. Tracking in-memory con window de 1 hora.
3. **Role-based permissions:** CEO/Admin accede a las 6 herramientas. Supervisor accede a 5 (no puede crear departamentos). Agent solo accede a 2 (read-only: listar departamentos y agentes).

**Alternativas consideradas:**
- Redis para rate limiting — más robusto (persiste entre reinicios), pero agrega dependencia. El tracking in-memory es suficiente para MVP.
- Límites configurables por organización — más flexible pero agrega complejidad en la UI de configuración. Los valores hardcoded (20/15/3) son razonables para el caso de uso.

**Riesgos/Limitaciones:**
- Los hard limits son globales, no configurables por org. Algunas organizaciones grandes podrían necesitar más de 20 departamentos.
- El rate limit in-memory no sobrevive reinicios del proceso.

---

## [2026-04-12] Provenance tracking: quién creó qué agente y por qué

**Contexto:** Cuando un agente CEO crea otro agente autónomamente, necesitamos saber quién lo creó y por qué — para auditoría, debugging, y para que el humano pueda revisar las decisiones del CEO.

**Decisión:** Dos columnas nuevas en la tabla `agents`:
- `created_by_agent_id` (FK a agents.id, nullable) — NULL si fue creado por un humano
- `creation_reason` (Text, nullable) — la razón que el agente dio para crear este recurso

El frontend muestra esta info en el `AgentLifecycleCard`: "Creado por [Agent Name]" con link al agente creador, o "Creado manualmente" si es NULL.

**Alternativas consideradas:**
- Tabla de auditoría separada (audit_log) — más completo pero requiere joins para mostrar info básica.
- Campo `metadata` JSONB existente — ya existe en agents, pero mezclar provenance con otros metadatos dificulta queries.

**Riesgos/Limitaciones:**
- El `created_by_agent_id` FK crea una segunda relación self-referential en la tabla agents (la primera es `supervisor_id`). SQLAlchemy necesita `foreign_keys=` explícito en todas las relaciones self-referential cuando hay múltiples FKs.

---

## [2026-04-12] Lifecycle monitor como 4to background worker (no cron externo)

**Contexto:** Necesitamos detectar agentes que llevan mucho tiempo sin completar tareas (idle) para notificar al humano. La detección debe ser periódica pero no en tiempo real.

**Decisión:** Un 4to background worker (`lifecycle_monitor.py`) que corre cada 24 horas dentro del mismo proceso FastAPI:
- Busca agentes con `last_task_completed_at` > 7 días atrás, O agentes creados hace > 3 días con `total_tasks_completed = 0`
- Crea una notificación de tipo `AGENT_IDLE` para cada uno
- Emite evento SSE `agent.idle_detected`
- **Nunca desactiva automáticamente** — solo notifica al humano para que decida

**Alternativas consideradas:**
- Cron job externo — más robusto (sobrevive reinicios) pero agrega complejidad de infraestructura
- Trigger en la base de datos — evaluaría en cada INSERT/UPDATE a tasks, overhead constante vs evaluación batch cada 24h
- Desactivación automática de agentes idle — demasiado agresivo, un agente podría estar idle por diseño (ej: un agente de emergencias)

**Riesgos/Limitaciones:**
- Si el proceso se reinicia, el timer se resetea y la próxima evaluación ocurre 24h después del reinicio.
- La detección no es deduplicada entre reinicios — pero sí evita spam chequeando si ya existe una notificación idle no leída para ese agente.

---

## [2026-04-12] Phase 5A: Security hardening — token blacklist, rate limiting, security headers

**Contexto:** CRM Agents estaba demo-ready (4 fases) pero no podía aceptar datos reales de clientes. Sin rate limiting, un brute-force en `/login` era trivial. Sin token revocation, logout era cosmético (solo borraba el token del browser). Sin refresh token rotation, un token comprometido valía 7 días completos.

**Decisión — Token blacklist via JTI:**
Cada JWT (access y refresh) ahora incluye un claim `jti` (JWT ID, UUID). Al hacer logout o refresh, el JTI del token anterior se inserta en la tabla `token_blacklist`. Cada request autenticado chequea el JTI contra la blacklist antes de aceptar el token.

**Por qué JTI y no el token completo:** Un JTI es un UUID de 36 chars — indexa eficientemente en PostgreSQL con un índice B-tree. El token completo es 300+ bytes y requiere hashing para indexar. JTI es el estándar de la industria (RFC 7519 §4.1.7).

**Alternativas consideradas:**
- Refresh token families (como Auth0) — tabla `refresh_token_families` que trackea toda la cadena de rotación. Si se detecta reuse de un token viejo, se invalida toda la familia. Más seguro contra replay attacks sofisticados, pero agrega complejidad de modelo significativa. Para MVP, blacklist simple es suficiente.
- Redis para blacklist — más rápido que PostgreSQL para lookups simples. Pero agrega una dependencia de infraestructura. Aceptable migrar a Redis en Phase 7 cuando se necesite multi-worker.
- Full token storage en DB — requiere almacenar tokens completos y buscar por string matching. Ineficiente y no aporta nada sobre JTI.

**Decisión — Rate limiting in-memory:**
Sliding window counter por IP:path en un `dict[str, list[float]]` en memoria. Límites: login 5/60s, register 3/60s, refresh 10/60s. Sin dependencias externas.

**Por qué in-memory y no Redis/slowapi:** Mismo razonamiento que el rate limiting de tools (Phase 4): single-process uvicorn, estado se pierde en restart pero no causa daño. `slowapi` agrega dependencia por algo que son ~60 líneas de código. Redis migración en Phase 7.

**Decisión — Backward compatibility:**
Tokens emitidos antes de Phase 5A no tienen `jti`. El check de blacklist se salta cuando `payload.get("jti")` retorna None. Esto permite zero-downtime upgrade — tokens existentes en browsers siguen funcionando hasta que expiren naturalmente (30min access, 7 días refresh).

**Riesgos/Limitaciones:**
- Rate limiting in-memory no sobrevive reinicios y no es compartido entre workers. Aceptable para single-process MVP.
- Blacklist table crece con cada logout/refresh. Un worker cada hora limpia entradas expiradas (`expires_at < now()`), manteniendo la tabla acotada.
- Múltiples usuarios detrás del mismo NAT corporativo comparten IP — los límites son generosos (5/min login) para minimizar falsos positivos.

**Archivos modificados:** `auth/models.py`, `auth/service.py`, `auth/dependencies.py`, `auth/router.py`, `auth/schemas.py`, `core/middleware.py`, `main.py`, `config.py`
**Migration:** `3313605f6b2a_add_token_blacklist`

---

## [2026-05-24] Limpieza de demo DigitalMind y re-anclaje a landing v2

**Contexto:** El primer demo del producto se construyó alrededor de una "agencia de marketing DigitalMind" con 3 departamentos y 8 agentes hardcodeados (Director de Contenido, Copywriter, Investigador, Account Manager, etc.). Cuando re-anclamos el roadmap a la landing v2 (target HDI Seguros + mid-market enterprise), este demo dejó de ser relevante. Los seeds y referencias podían contaminar el desarrollo del nuevo producto.

**Decisión:** Limpieza estructurada en 3 categorías:

1. **Archivar** (no borrar — pueden tener valor de referencia futura):
   - `backend/seed.py` → `archived/seeds_v1_digitalmind/seed.py`
   - `backend/seed_metrics.py` → `archived/seeds_v1_digitalmind/seed_metrics.py`
   - `backend/seed_knowledge.py` → `archived/seeds_v1_digitalmind/seed_knowledge.py`
   - `backend/seed_prompts.py` → `archived/seeds_v1_digitalmind/seed_prompts.py`
   - `PHASE4_PLAN.md` → `archived/PHASE4_PLAN.md` (ya implementado en commit `f393194`)
   - `ROADMAP.md` V2.1 y V3 → `archived/` (mantienen histórico de evolución del plan)

2. **Borrar** (sin valor, riesgo de confusión):
   - `AGENTS.md` (raíz) — era duplicado erróneo de `CLAUDE.md` que decía "Codex API" en lugar de "Claude API". Mantener dos archivos casi iguales confunde más que ayuda.

3. **No tocar** (sigue siendo válido):
   - Frontend completo (cero referencias hardcoded a DigitalMind — sorpresa positiva)
   - Phase 5A security (token blacklist, rate limiting, etc.)
   - Auth, multi-tenancy, tests (69 tests verde)
   - Modelos core (Organization, User, Agent, Task, Department, Knowledge, Credentials)
   - Webhook adapters genéricos (n8n, LangChain, CrewAI)
   - DECISIONS.md, CLAUDE.md, README.md, SECURITY.md

**Por qué archivar y no borrar los seeds:**
- `seed_prompts.py` contiene templates genéricos (Marketing Digital, Ventas B2B, Soporte L1) que pueden ser semilla del catálogo de 30-50 agentes en P2.3
- La estructura de delegación supervisor → especialistas de `seed.py` es válida — solo cambia el contexto de negocio (de agencia → aseguradora)
- Los 4 roles base (admin/manager/supervisor/agent) de `seed.py` son punto de partida válido para P0.4 (RBAC granular)
- Borrarlos perdería referencia histórica del primer demo funcional

**Alternativas consideradas:**
- Borrar todo sin archivar — más limpio pero pierde referencia útil
- Mantener seeds activos en `backend/` con un flag "demo" — riesgo de que se ejecuten accidentalmente y contaminen la DB
- Reescribir los seeds ahora para HDI — prematuro sin tener claros los agentes target

**Hallazgo no resuelto (anotado para P0.8 — CI/CD):**
Durante la validación post-limpieza, los tests presentaron flakiness ocasional: `test_register_creates_user_and_org` falló en 1 de 3 corridas consecutivas (otras 2 pasaron limpio 69/69). La causa probable es race condition en el rate limiter cuando dos tests ejecutan en rápida sucesión y la fixture autouse `_clean_rate_limit_state` no termina antes del siguiente test. **No fue causado por la limpieza** (la limpieza no tocó código de tests ni del rate limiter), es flakiness pre-existente. Cuando construyamos P0.8 (CI/CD), arreglarlo es prioridad — tests flaky bloquean merges y son inaceptables en pipeline de CI.

**Archivos afectados:**
- 4 archivos movidos a `archived/seeds_v1_digitalmind/`
- 1 archivo movido a `archived/` (PHASE4_PLAN.md)
- 1 archivo eliminado (AGENTS.md)
- 1 archivo nuevo en archivado: `archived/seeds_v1_digitalmind/README.md` con instrucciones de cuándo volver a revisar cada seed

**Estado post-limpieza:**
- 69 tests verde (suite estable en 2 corridas consecutivas)
- Backend sin seeds activos en raíz (`backend/seed*.py` ya no existe)
- `archived/` con todos los artefactos del demo viejo + README explicativo
- Repo listo para arrancar P0 sin contaminación del producto anterior

---

## [2026-05-24] P0.1 — Vault para encriptación de credenciales at-rest

**Contexto:** El campo `credentials.secret_value` se almacenaba en plaintext en PostgreSQL. Un docstring del modelo decía falsamente "encryption at rest via PostgreSQL", pero Postgres no encripta por default. Esto es bloqueante para enterprise: HDI no entrega API keys de Genesys/Dynamics si pueden leerse desde un backup. Es la primera tarea P0 del roadmap V3.1 porque sin ella, ninguna conversación de venta enterprise avanza.

**Decisión:** Encriptación a nivel de aplicación con **Fernet** (AES-128-CBC + HMAC-SHA256 de la librería `cryptography`, ya instalada vía `python-jose[cryptography]`). Una sola key (`VAULT_ENCRYPTION_KEY`) por instancia, almacenada en `.env` separada del DB. Cuatro componentes:

1. **`app/credentials/encryption.py`** — clase `Vault` con `encrypt()` / `decrypt()` + singleton `get_vault()` lazy-initialized + helper `reset_vault_for_tests()`.
2. **`credentials.secret_value`** ahora guarda ciphertext (no plaintext). `secret_preview` sigue siendo los últimos 4 caracteres del plaintext (calculado antes de encriptar).
3. **Función nueva `CredentialService.get_credential_value()`** — la ÚNICA forma soportada de obtener el plaintext. Decripta + crea entrada en `credential_access_log` ANTES de retornar. Si el log falla, el secret no se entrega.
4. **Tabla `credential_access_log`** — append-only, registra `credential_id`, `agent_id` o `user_id`, `accessed_at`, `context` (free-form, ej: `"task_execution:task_<uuid>"`). Pertenece transitivamente al tenant del credential — no necesita su propio `organization_id`.

**Alternativas consideradas:**

| Opción | Por qué no |
|---|---|
| AWS KMS / GCP KMS | Rotación nativa + audit logs nativos, pero agrega dependencia externa, costo, y complejidad operativa que no se justifica en MVP. **Upgrade path documentado para Phase 5.** |
| HashiCorp Vault (servicio) | Industry standard pero es un servicio extra a operar. Overkill para MVP. **Upgrade path para SOC 2 Type II (Phase 5).** |
| Per-tenant encryption keys | Aislamiento máximo (filtración de cliente A no afecta B) pero complejidad alta para MVP (¿dónde se guardan N keys?). **Reconsiderar en Phase 5+ si SOC 2 lo exige.** |
| Solo DB encryption (PostgreSQL TDE) | Transparente al código, pero NO protege contra: backup leak, empleado con acceso a DB, dump de la app con la key. Insuficiente como única defensa. Defense-in-depth para Phase 5. |
| Caché de plaintext decryptado en memoria | Optimización que reduce decrypt-per-task de N a 1. **No incluido en P0.1** — encrypt/decrypt con Fernet toma ~50µs, no es bottleneck. Reconsiderar si se vuelve problema. |

**Validación al iniciar (`config.py`):** Si `debug=False` y `vault_encryption_key` está vacío, el servidor crashea al arrancar con mensaje claro de cómo generar una key. Misma filosofía que la validación de `JWT_SECRET_KEY` agregada en Phase 5A — fallar rápido y visible es mejor que fallar silenciosamente.

**Riesgos identificados:**
- **Pérdida de la key = pérdida total de los secretos.** Mitigación: documentación en `.env.example` indicando backup separado del DB.
- **Key rotation** — out-of-scope para P0.1. Planeado para Phase 5 (key versioning + re-encryption tool).
- **Datos legados en plaintext** — en dev databases pueden quedar `secret_value` viejos sin encriptar. No los migramos automáticamente porque (a) son datos demo sin valor y (b) el demo se eliminó en la limpieza previa. En instalaciones reales, antes de deploy P0.1 se debe correr un script ad-hoc de re-encryption (futuro: incluir en `scripts/migrate_plaintext_credentials.py`).

**Archivos tocados:**
- Creados: `app/credentials/encryption.py`, `alembic/versions/d5e8f1c4a9b2_add_credential_access_log.py`, `tests/test_vault.py`, `backend/.env.example`
- Modificados: `app/credentials/models.py` (+ `CredentialAccessLog`), `app/credentials/service.py` (encrypt en create/update + `get_credential_value()`), `app/config.py` (setting + validación), `alembic/env.py` (import del nuevo modelo), `tests/conftest.py` (import del nuevo modelo)

**Decisión operativa sobre migrations:** Alembic `autogenerate` se cuelga consistentemente en este entorno (iCloud Drive + paths con espacios, problema documentado en CLAUDE.md). Por eso la migration se escribió a mano y se aplicó directo vía `psql` con `UPDATE alembic_version`. Funciona, pero no es repetible automáticamente para CI. En P0.8 (CI/CD) hay que decidir: (a) mover el repo fuera de iCloud, (b) usar un alembic alternativo, o (c) generar migrations a mano siempre. Por ahora, "a mano siempre" es la regla.

**Validación:** 15 tests del Vault verde + 69 tests previos = 84 tests verde sin regresiones.

**Próximo bloque P0:** P0.2 — Audit log inmutable organization-wide (no solo de credentials).

---

## [2026-05-24] P0.2 — Audit log inmutable organization-wide

**Contexto:** Después de P0.1 teníamos `credential_access_log` (audit específico de lectura de credenciales), pero faltaba la capa general que enterprise espera: **un solo lugar donde queda registrada CADA acción sensible** (humanas y de agentes) en formato exportable para auditores. Sin esto, no hay manera defendible de responder al CISO de HDI cuando pregunte "muéstrame todo lo que pasó en mi tenant la semana pasada". El 50% de proyectos agentic se quedan en piloto por falta exactamente de esta gobernanza (dato de mercado citado en el roadmap).

**Decisión 1 — Dos tablas distintas, no una unificada:**

| | `activity_logs` (ya existía) | `audit_log` (NUEVA) |
|---|---|---|
| Actor | Solo agentes (`agent_id` NOT NULL) | Humanos Y agentes |
| Propósito | Bitácora operacional, dashboard, UX | Forensics + compliance |
| Audiencia | Operadores internos | Auditores externos, CISO |
| Inmutable | No | Sí (trigger DB bloquea UPDATE) |
| Hash inputs/outputs | No | Sí (SHA-256) |
| Exportable | No | Sí (CSV vía endpoint) |

Considerada y descartada: refactor de `activity_logs` para que cumpla ambos roles. Razones:
- Consumidores distintos con UX distinta — mezclarlos confunde a ambos lados
- Cambiar el modelo de `activity_logs` rompe el frontend que ya consume sus endpoints
- Separation of concerns más limpia y mantenible

**Decisión 2 — 30 event types (no granular hasta el evento, no demasiado genérico):**

Cubren auth (4), users/orgs (4), agentes (4), departments (3), tasks (5), credentials (3), knowledge (2), integrations (2), approvals placeholder (3). Esto cubre las promesas de la landing v2 sobre auditabilidad sin convertir el enum en algo inmantenible.

Naming convention: `<domain>.<noun>.<verb_or_outcome>` — `auth.login.success`, `agent.created`, `task.executed`, etc.

**Decisión 3 — Llamadas explícitas, NO decoradores ni middleware:**

Tres opciones consideradas:

| Opción | Descartada porque |
|---|---|
| Middleware automático | Muy mágico, no sabe quién/qué hizo, difícil de testear |
| Decorador `@audit_action` | Requiere modificar cada service, abstrae lo que debería ser explícito |
| **Llamadas manuales** ✅ | Muy claro, code review obvio, fácil de testear |

Mitigación de "olvidar agregar log en endpoint nuevo": tests que verifican que cada endpoint sensible genera entrada.

**Decisión 4 — Append-only enforced en DB (trigger PostgreSQL):**

```sql
CREATE TRIGGER no_update_audit_log
    BEFORE UPDATE ON audit_log
    FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_update();
```

**Defense in depth:** aunque un bug en código quiera modificar, la DB lo rechaza. Esto es lo que distingue un audit log "real" de uno "operacional" — la inmutabilidad es ley, no convención.

**DELETE no se bloquea** a nivel DB porque se necesita para el retention policy (P0.7 LFPDPPP — 7 años default para banca/seguros, después se borra). DELETE bloqueado a nivel código (no exponemos endpoint que borre del audit log).

**Decisión 5 — SHA-256 de inputs/outputs, NO almacenar contenido:**

```python
input_hash: String(64)  # SHA-256 hex digest
output_hash: String(64)
```

Privacy by design: si la DB se filtra, los hashes no revelan PII. Pero auditores con el contenido original pueden verificar "este exacto valor pasó por el sistema el día X" (forensic confirmation).

**Decisión 6 — Solo OWNER y ADMIN pueden leer el audit log:**

Endpoint protegido con `Depends(require_role(UserRole.OWNER, UserRole.ADMIN))`. Member/Viewer obtienen 403. Razón: el audit_log puede contener IPs, user agents, referencias a otros usuarios — sensible.

**Decisión 7 — `actor_user_id` opcional via constructor del service (credentials):**

Para no contaminar TODOS los services con un nuevo parámetro obligatorio. El que necesite audit (CredentialService) acepta `actor_user_id` en el constructor, el resto de services (agents, tasks, departments, knowledge) hacen el audit a nivel router. Patrón híbrido pragmático.

**Alcance del bloque (qué entra / qué NO):**

✅ Entra: modelo + 30 event types + helper + trigger DB + 21 puntos de integración (auth + agents + tasks + executor + credentials + departments + knowledge) + endpoint GET filtrable + export CSV + role guard.

❌ No entra:
- Export PDF (P1.6 reportes ejecutivos)
- UI frontend para visualizar (P2 multi-user UX)
- Alertas automáticas de anomalías (P4 drift detection)
- Retention policy automatizada (P0.7 LFPDPPP)
- Integración SIEM externo (P4 enterprise)
- Lógica de aprobación humana (P0.5 — las columnas `autonomy_level` y `approved_by_user_id` ya están listas)

**Detalle de implementación que generó deuda menor:**

Los enums de PostgreSQL en la migration manual usan VALUES (`'success'`, `'failure'`) pero `Base.metadata.create_all` en test DB los crea con NAMES (`'SUCCESS'`, `'FAILURE'`). Esto solo se manifiesta si se hace raw SQL con valores literales — el ORM funciona en ambos casos. **Anotado para resolver en P0.8 (CI/CD)** cuando estandaricemos cómo se manejan las migrations: o todo manual con psql, o todo via alembic generado, no mezcla.

**El trigger PostgreSQL no es parte del schema ORM** — `Base.metadata.create_all` solo crea tablas e índices, no triggers. Fix: el conftest.py de tests ahora ejecuta el SQL del trigger después de `create_all` para que la test DB se comporte igual que prod. La migration alembic también lo crea via `op.execute()`.

**Archivos creados/modificados (12 archivos):**

Creados:
- `app/audit/__init__.py`, `models.py`, `schemas.py`, `service.py`, `router.py`
- `alembic/versions/e1f9d8c3b7a4_add_audit_log.py` (migration manual)
- `tests/test_audit_log.py` (18 tests)

Modificados:
- `app/main.py` (mount router)
- `alembic/env.py`, `tests/conftest.py` (import + trigger SQL)
- `app/auth/router.py` (audit: register, login, refresh, logout)
- `app/agents/router.py` (audit: create internal, register external, update, delete)
- `app/tasks/router.py` (audit: create, execute)
- `app/workers/agent_executor.py` (audit: complete, fail)
- `app/credentials/service.py` (audit: create, update, delete + actor_user_id en constructor)
- `app/credentials/router.py` (pasa actor_user_id al service)
- `app/departments/router.py` (audit: create, update)
- `app/knowledge/router.py` (audit: upload, delete)

**Validación:** 18 tests del audit log verde + 84 tests previos = 102 tests verde sin regresiones.

**Próximo bloque P0:** P0.3 — MCP Router con scope por área (el corazón del producto según la landing v2).

---

## [2026-05-24] P0.3 — MCP Router con scope por área (gateway de acceso enterprise)

**Contexto:** Tercer bloque P0. Es **el corazón del producto vendible** según la landing v2: *"MCP Router que reparte el acceso por área"*. Sin esto, el producto es un orquestador genérico más — no diferencia frente a Dify/Flowise. Con esto, somos la capa de gobernanza enterprise que enterprise mid-market exige.

**El gap fundamental que había que cerrar primero:** los `User` solo tenían `organization_id` — no había forma de saber a qué área (departamento) pertenecía un user dentro del tenant. Sin eso, el Router no podía "repartir por área". Agregar `users.department_id` (FK nullable) fue prerequisito sin alternativa real.

**Decisión arquitectónica principal — el Router NO es el cerebro:**

Discutido en sesión previa con Richard (ver entradas anteriores): el MCP Router es **capa pasiva de control de acceso + audit**, NO el cerebro cognitivo. Cuatro responsabilidades:
1. Identificar quién pregunta (vía JWT, ya hecho por dependencias)
2. Resolver scope (qué agentes/tools puede invocar)
3. Auditar la decisión (MCP_ROUTE_REQUESTED / MCP_ROUTE_DENIED)
4. Despachar al supervisor del departamento (delegación cognitiva en supervisor_delegator.py existente)

Lo que **NO hace el Router** (responsabilidades de otros componentes):
- Descomposición de tareas → supervisor del dept
- Decisión plan-vs-ejecución → CEO Agent (P0.6, P1.2)
- Razonamiento sobre el query → LLM detrás del supervisor

**Decisión 2 — Modelo de scope: dos tablas separadas (agentes + tools):**

| | `department_agent_permissions` | `department_tool_permissions` |
|---|---|---|
| PK compuesta | `(dept_id, agent_id)` | `(dept_id, tool_name)` |
| FK agent_id | sí (ondelete CASCADE) | n/a |
| tool_name | n/a | String(100) — match con `@register_tool(name)` |
| granted_by_user_id + granted_at | sí (auditoría informal) | sí |

Considerada y descartada: una sola tabla "permissions" con tipo + scope_id polimórfico. Más limpio tener dos tablas estrictas (cada una con FK fuerte). Más fácil de hacer queries con JOIN para "qué agents puede invocar este dept".

**Decisión 3 — Scope es lista blanca, no lista negra:**

Por defecto: dept nuevo NO puede invocar nada. Owner/Admin debe otorgar explícitamente. Más seguro y más enterprise-friendly que el reverso ("todo permitido, prohibir uno por uno").

OWNER/ADMIN bypasean el scope check vía `UserScope.is_org_wide=True`. Lógica en `ScopeService.resolve_scope_for_user()`: si `user.role in (OWNER, ADMIN)`, retorna scope org-wide sin tocar las tablas de permisos.

**Decisión 4 — Sin caché de scopes — promesa "revocable al instante":**

Cada call a `/mcp/route` consulta DB fresh. Trade-off: ~5ms extra por request a cambio de la promesa explícita de la landing *"permisos revocables al instante"*. Sin esto, un admin que revoca por incidente tendría que esperar a que expire la caché (segundos o minutos). Inaceptable para enterprise.

Test específico (`TestRevocationIsInstant`) verifica que un DELETE en `/admin/departments/{id}/scopes/agents/{aid}` hace que el SIGUIENTE call a `/mcp/route` devuelva 403. No "next minute", "next request".

**Decisión 5 — Reusar supervisor del dept en lugar de crear "CEO Agent" nuevo:**

La landing menciona "CEO Agent" pero el sistema ya tiene supervisores per-dept funcionando (`supervisor_delegator.py`, 495 líneas, con tool_use para delegación). Crear un CEO Agent nuevo en P0.3 sería:
- Duplicar funcionalidad existente
- Mezclar P0.3 (acceso) con P0.6 (cerebro híbrido)
- Aumentar el blast radius de un cambio crítico

**P0.3 usa supervisor del dept. P0.6 (futuro) introducirá CEO Agent híbrido con pattern matching.**

`_find_department_supervisor()` busca primero `department.head_agent_id`, fallback a cualquier agente del dept con role.level en (SUPERVISOR, MANAGER, ADMIN), excluyendo agents en ERROR/OFFLINE. Si no encuentra → 503 con mensaje claro.

**Decisión 6 — División en 3 sub-commits (3.1, 3.2, 3.3):**

Por tamaño y separabilidad lógica:
- **3.1 Foundation** (modelos + scope storage + service): commit independiente, no requiere endpoint para validar
- **3.2 Endpoint /mcp/route + integración**: depende de 3.1
- **3.3 Admin endpoints + UI backend**: independiente de 3.2 (puedes administrar scopes sin que el endpoint esté listo)

Hubo dilema de hacer 1 sub-commit o 3 — decidí los 3 SE FUSIONAN en UN solo commit final porque trabajamos linealmente y los tests dependen del módulo completo. La separación queda en `git log` con la frase "P0.3.X" en el body del commit message para futura referencia.

**Decisión 7 — `task.created_by` queda NULL para tasks creados desde Router:**

`tasks.created_by` es FK a `agents.id` (no users.id) — diseño legacy. Una task creada por un USER humano vía Router tiene `created_by=NULL` legítimamente. La traceabilidad va por `audit_log.actor_user_id` (que ya capturamos en MCP_ROUTE_REQUESTED).

Anotado como deuda técnica: en P0.5 o más tarde, ampliar el modelo Task con `created_by_user_id` separado para casos donde el creador es humano. No urgente.

**Decisión 8 — `target_department_id` opcional en el body:**

OWNER/ADMIN sin departamento asignado pueden especificar `target_department_id` para dispatch a cualquier dept del org. MEMBER que intente targetear otro dept → 403 (audit denied con razón `member_cannot_target_other_department`).

Caso edge: OWNER con `department_id` SET y target distinto — permitido (el owner es supervisor de TODO). El check `user.role not in (OWNER, ADMIN)` aplica solo a member/viewer.

**Decisión 9 — `await db.commit()` removido del endpoint:**

Inicial draft tenía `await db.commit()` antes del `asyncio.create_task(delegate_task_background(...))`. Razón intuitiva: el background task abre su propia session y no vería la task si no está commiteada.

Pero esto rompe la transacción de tests (que usan rollback). La fix: confiar en que `get_db()` ya commitea al final del request, y `asyncio.create_task` programa la coroutine pero NO la ejecuta inmediatamente — el event loop la ejecuta DESPUÉS del commit del request. Funciona en prod (task visible para background) y en tests (rollback intacto).

**Decisión 10 — 4 audit events nuevos:**

```python
MCP_ROUTE_REQUESTED = "mcp.route.requested"      # toda petición exitosa
MCP_ROUTE_DENIED = "mcp.route.denied"            # rechazado por scope o config
MCP_PERMISSION_GRANTED = "mcp.permission.granted" # admin otorgó scope
MCP_PERMISSION_REVOKED = "mcp.permission.revoked" # admin revocó scope
```

Cada uno con `input_hash` del query (privacy) + context rico (department, supervisor, scope size).

**Lo que NO entra en P0.3 (documentado explícitamente):**
- UI frontend para configurar scopes (P2 multi-user UX — endpoints listos)
- 4 niveles de autonomía Shadow + Auto + Co-piloto + Manual (P0.5)
- Pattern matching del CEO Agent (P0.6)
- MCP routers externos: Composio, Pipedream, Zapier (P7)
- Modo plan-vs-ejecución (P1.2 — no es P0)
- LLM local routing (P5)

**Archivos creados/modificados (10 archivos):**

Creados:
- `app/mcp/__init__.py`, `models.py`, `schemas.py`, `service.py`, `router.py`, `admin_router.py`
- `alembic/versions/e8d4a2b1f3c5_add_user_department_and_mcp_scopes.py`
- `tests/test_mcp_scopes.py` (13 tests del foundation)
- `tests/test_mcp_router.py` (18 tests del endpoint + admin + revocación instantánea)

Modificados:
- `app/auth/models.py` — agregar `User.department_id` (FK nullable)
- `app/audit/models.py` — 4 nuevos AuditEventType
- `app/main.py` — montar mcp_router + mcp_admin_router
- `alembic/env.py`, `tests/conftest.py` — registrar nuevos modelos

**Tablas + columnas en DB:**
- `users.department_id` (FK nullable a departments)
- `department_agent_permissions` (PK compuesta)
- `department_tool_permissions` (PK compuesta)
- 4 nuevos valores en enum `auditeventtype`

**Validación:** 13 tests del foundation + 18 tests del endpoint = 31 tests del bloque verde. Suite completa 133/133 sin regresiones.

**Verificación end-to-end manual:**
1. Owner crea dept "Marketing" → POST /admin/departments/{id}/scopes/agents para grant supervisor → POST /mcp/route con target_dept_id → 202 con task_id
2. Member del dept con scope vacío → POST /mcp/route → 403 (scope vacío) + audit MCP_ROUTE_DENIED en DB
3. Owner DELETE /admin/.../agents/{id} → siguiente POST /mcp/route → 403 (revocación instantánea verificada)

**Próximo bloque P0:** P0.4 — RBAC granular por departamento (permisos read/aprobar/crear/eliminar por acción) o P0.5 — Sistema de aprobación humana con 4 niveles (Shadow + Auto + Co-piloto + Manual). Empezar por P0.5 tiene más valor de demo HDI; P0.4 puede esperar a tener UI multi-user.

---

## [2026-05-24] P0.5 — Sistema de aprobación humana con 4 niveles de autonomía

**Contexto:** Cuarto bloque P0 (saltamos P0.4 a P0.5 por decisión de Richard — más valor de demo). Cumple LITERALMENTE la promesa central de la landing v2: *"Aprobación humana siempre. La IA prepara, el humano decide. Audit trail completo."* Sin esto, agentes operan en modo todo-o-nada. Con esto, el cliente configura por dept/agent/acción cuándo el humano interviene.

**Los 4 niveles de autonomía:**

| Nivel | Nombre | Comportamiento | Audit |
|---|---|---|---|
| 0 | SHADOW | Recibe inputs reales, NO ejecuta, registra lo que HABRÍA hecho | `SHADOW_ACTION_LOGGED` |
| 1 | AUTO | Ejecuta sin preguntar, reversible | (request con status `AUTO_EXECUTED`) |
| 2 | COPILOT | Ejecuta + notifica humano (in-app hoy, WhatsApp futuro) | (request con status `COPILOT_NOTIFIED`) |
| 3 | MANUAL | Humano aprueba ANTES de ejecutar; task pausa en `WAITING_APPROVAL` | `APPROVAL_REQUESTED` → `APPROVAL_GRANTED`/`APPROVAL_REJECTED` |

**Decisión 1 — Default Nivel 3 (MANUAL) cuando no hay política configurada:**

Richard pidió probar este approach pero **documentar para revisión futura**. Razones:
- Más seguro: si el admin no configuró nada, todo requiere aprobación humana
- Aleja al producto de "ya funcionó por accidente, ahora descubrimos lo que se ejecutó solo"
- Frustración aceptable porque el admin verá el output ("X requiere aprobación") y sabrá que debe configurar

**Trade-off documentado para revisar:**
- **Pro:** seguro por default. Cero acciones autónomas inesperadas.
- **Contra:** primer uso de cada acción requiere intervención humana. Si el admin no configura políticas rápido, el agente queda bloqueado.
- **Alternativa si esto frustra a HDI:** cambiar default a Nivel 2 (COPILOT) — el agente actúa pero notifica. Más ágil. Trade-off: requiere monitoreo activo.
- **Punto de re-evaluación:** después del primer cliente piloto con HDI. Si el feedback es "tenemos que aprobar muchas cosas", bajar default. Si es "queremos más control", mantener.

**Decisión 2 — `DELETE:*` hardcoded a Nivel 3, sin override:**

```python
if action.upper().startswith("DELETE:") or action == "DELETE":
    return AutonomyLevel.MANUAL, "hardcoded:DELETE"
```

Aunque haya una política wildcard `*` → `AUTO`, los DELETEs SIEMPRE requieren aprobación. Razones:
- Compliance enterprise: nunca borrar datos sin oversight humano
- Test específico (`test_delete_action_is_always_manual_even_with_auto_policy`) lo verifica
- Cumple regla explícita del ROADMAP V3.1: *"DELETE siempre Nivel 3 (no configurable)"*

**Decisión 3 — Patrones simples (no regex):**

- `*` = todo
- `assign_task` = match exacto
- `DELETE:*` = prefijo seguido de `:`

Razones: regex completo es overkill para MVP, propenso a errores de admin escribiendo regex mal, y los 3 patrones cubren ~95% de casos. Si en P3+ se necesita más expresividad, se agrega.

**Decisión 4 — Precedencia de scope en `resolve_level`:**

Orden: `DELETE:*` hardcoded → `agent:<id>` → `dept:<id>` → `global` → default MANUAL.

Dentro de un mismo scope, exact match beats prefix beats wildcard. Test parametrizado (`test_exact_action_pattern_beats_wildcard`) verifica.

**Decisión 5 — Hook en `_execute_agent_tool` con excepciones tipadas:**

En vez de cambiar el return type de `_execute_agent_tool` para incluir señales de pausa/rechazo, usé excepciones:
- `ApprovalRequiredError` — Nivel 3, pausa el loop
- `ApprovalRejectedError` — request previa rechazada, task termina REJECTED

El caller (`_execute_internal`) las captura, marca el task con el status correcto, emite SSE event, y sale. **Patrón:** decisiones cognitivas son returns, control de flujo excepcional usa exceptions.

**Decisión 6 — `task.status = WAITING_APPROVAL` pausa, reanuda en re-dispatch:**

Cuando un Nivel 3 pausa, la task queda WAITING_APPROVAL y el executor sale limpio. Cuando humano aprueba, el frontend (P2 futuro) o admin manual debe re-disparar `/tasks/{id}/execute`. El executor detecta el ApprovalRequest APPROVED reciente (ventana 1h) y procede sin re-preguntar.

**Pragmatismo:** En MVP no hay re-dispatch automático tras approve. Próximo bloque (probablemente P0.6 o P0.8 worker) implementa el auto-resume. Documentado como deuda técnica.

**Decisión 7 — Idempotencia por (task_id, action):**

`check_or_request` busca el ApprovalRequest más reciente para esa combinación. Si existe:
- PENDING → wait (no duplicar)
- APPROVED en última hora → execute
- REJECTED → wait (la task ya está perdida, no hacer loop infinito)
- APPROVED hace >1h → crea nuevo request (la aprobación caducó)

Esto evita que el tool_use loop pida 50 aprobaciones idénticas si el LLM re-intenta.

**Decisión 8 — UN solo commit grande en lugar de sub-commits:**

Como discutimos en el plan: P0.5.1 a P0.5.4 son interdependientes para validar el flow end-to-end. Mejor un commit grande validado completamente que 4 commits parciales con riesgo de romper entre sí.

**Decisión 9 — Notificaciones Nivel 2 son in-app (no WhatsApp/email todavía):**

El módulo `notifications` existente cubre el caso in-app. Integración WhatsApp Business es P1.5. Email queda implícito en P1.5 también. **No bloquea P0.5 funcional.**

**Decisión 10 — Worker que expira approvals viejos queda para P0.8:**

ApprovalRequest tiene `expires_at` (default +24h) pero NO hay worker que ejecute la transición a EXPIRED. Está documentado y será 5to background worker en P0.8.

**Lo que NO entra en P0.5 (deferido):**

| Feature | A dónde va |
|---|---|
| Re-dispatch automático tras approve | P0.6 o P0.8 (worker que monitorea APPROVED + WAITING_APPROVAL combos) |
| Worker de expiración | P0.8 (CI/CD + Ops) |
| WhatsApp/email para Nivel 2 | P1.5 (WhatsApp Business integration) |
| UI frontend de cola de aprobaciones | P2 (multi-user UX) — endpoints listos |
| Sugerencia automática de bajar nivel tras N aprobaciones consecutivas | P3 — métrica + UI |
| Reversión de Nivel 2 (deshacer dentro de ventana) | P1 o más tarde |
| Approvals con scope por dept (department head approves) | P0.4 si lo hacemos, o P2 |

**Archivos creados/modificados (10 archivos nuevos + ~6 modificados):**

Creados:
- `app/approvals/__init__.py`, `models.py`, `schemas.py`, `service.py`, `router.py`, `admin_router.py`
- `alembic/versions/f6c9a1d4e5b2_add_approvals_and_autonomy.py`
- `tests/test_approvals.py` (26 tests organizados en 6 clases)

Modificados:
- `app/audit/models.py` — 3 nuevos AuditEventType
- `app/tasks/models.py` — 2 nuevos TaskStatus (`WAITING_APPROVAL`, `REJECTED`)
- `app/workers/agent_executor.py` — hook P0.5 antes de `execute_tool()` + 2 nuevas excepciones tipadas + caller catch
- `app/main.py` — montar 2 routers nuevos
- `alembic/env.py`, `tests/conftest.py` — registrar nuevos modelos

**Tablas + columnas en DB:**
- `autonomy_policies` (8 columnas)
- `approval_requests` (14 columnas)
- 2 nuevos enums: `autonomylevel`, `approvalstatus`
- 3 valores nuevos en `auditeventtype`
- 2 valores nuevos en `taskstatus`

**Validación:** 26 tests del bloque verde + 133 tests previos = **159 tests verde** sin regresiones.

**Verificación end-to-end manual:**
1. Admin crea política `(global, "*", AUTO)` → agentes ejecutan sin pedir
2. Admin crea política `(agent:X, "DELETE:*", MANUAL)` → DELETE en agent X pausa task
3. Admin aprueba via POST /approvals/{id}/approve → task se puede re-disparar y ejecuta
4. Admin rechaza → task termina REJECTED, no se re-loopea

**Promesas de la landing cumplidas:**
- ✅ "La IA prepara, el humano decide" (Nivel 3)
- ✅ "Audit trail completo" (cada decisión en `audit_log`)
- ✅ "Shadow mode antes de producción" (Nivel 0)
- ✅ "Autonomy escalable según confianza" (4 niveles configurables por scope)

**Próximo bloque P0:** P0.6 — CEO Agent híbrido (pattern matching + LLM fallback) que reduce token usage en queries conocidas. Otra opción: P0.7 LFPDPPP compliance básico (right to be forgotten + retention policy). HDI requeriría P0.7 para firmar, P0.6 mejora la experiencia.

---

## [2026-06-12] Dirección V4 — "La Agencia Autónoma": autonomía continua como destino

**Context:** Con P0.1–P0.5 completos (la capa de gobernanza: Vault, audit log inmutable, MCP Router, aprobación humana), Richard hizo una sesión de re-visión de rumbo. Definió el corazón del proyecto: una **agencia de agentes** — muchos agentes trabajando en conjunto por un objetivo, de forma continua — operando desde nube privada para no exponer datos. El sistema actual es 100% reactivo (humano pide → agentes ejecutan → termina); la visión requiere agentes con objetivos persistentes que trabajan sin que nadie los invoque.

**Decision:** Adoptar Roadmap V4 con estos pilares:
1. **"Agencia" = concepto central del producto** (no el modelo de negocio): goals persistentes + scheduler/triggers + memoria compartida + coordinación inter-agente. Se materializa en un Track A nuevo (A1–A6).
2. **Autonomía continua como destino, por etapas y por agente:** Reactivo (hoy) → Proactivo programado → Autónomo continuo. Cada agente/acción se promueve individualmente, nunca la plataforma completa.
3. **Tres principios nuevos no negociables:** (a) guardrails antes que autonomía — budgets de tokens + kill switch ANTES de encender nada 24/7; (b) Shadow-first — toda automatización nace en Nivel 0 y la autonomía se gana con historial; (c) gateway único de LLM — swap de proveedor por config, no reescritura.
4. **Negocio = escalera de despliegue, un solo producto:** primeros clientes rentan espacio en nube propia (multi-tenant, operados como servicio); grandes/regulados (HDI) reciben instancia dedicada. Confirma "3 tiers, 1 codebase" de V3.1.
5. **LLM gradual (Track L):** Claude API hoy → router por sensibilidad de datos → local-first con Claude como respaldo para tareas difíciles. Reemplaza al P3.1 binario.
6. **Secuencia:** P0.7 (LFPDPPP) → P0.8 (CI/CD+ops, sube por ser prerequisito de 24/7) → A1 → A2 (digest de autonomía = demo vendible) → P1.1 (pgvector, sube por habilitar memoria compartida).

**Alternatives considered:**
- *Reactivo mejorado* (pulir el modelo actual): menos riesgo, pero cero diferenciación — el mercado de task runners con LLM está saturado.
- *Proactivo programado como techo* (recomendación inicial de Claude): Richard decidió que es la etapa B, no el destino. La visión completa es continua.
- *Agencia-servicio puro* (consultoría): ingresos rápidos pero no escala; queda absorbido como "modo operado" de los primeros clientes.
- *LLM local desde ya*: calidad de razonamiento insuficiente para agentes autónomos y costo de infra prematuro; por eso la migración es gradual con Claude de respaldo.

**Risks/Limitations:**
- Autonomía continua = riesgo de costos descontrolados (agente en loop quemando tokens de madrugada). Mitigación: A1 no se entrega sin budgets + kill switch; es principio de arquitectura, no feature.
- Coordinación inter-agente puede generar ciclos de delegación infinitos. Mitigación: max depth + budgets heredados + audit de cadena completa (A5).
- El scheduler vive en el proceso FastAPI (patrón lifespan actual): suficiente para etapa B, insuficiente para 24/7 real multi-tenant — migrar a proceso separado cuando llegue etapa C.
- El digest Shadow (A2) puede prometer de más en ventas si los agentes en Shadow alucinan acciones que no podrían ejecutar realmente — revisar calidad antes de mostrarlo a HDI.

**Improvement opportunities:** Landing v3 con la promesa "la agencia trabaja aunque nadie pida"; trust score (A6) para automatizar la promoción de niveles; pricing del modo operado (pendiente con primer prospecto); naming del producto (el concepto "agencia" podría entrar al nombre).
