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
