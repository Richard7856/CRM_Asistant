import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.core.middleware import RequestTimingMiddleware
from app.auth.dependencies import get_current_user

# Import routers
from app.agents.router import router as agents_router
from app.departments.router import router as departments_router
from app.tasks.router import router as tasks_router
from app.activities.router import router as activities_router
from app.metrics.router import router as metrics_router
from app.interactions.router import router as interactions_router
from app.improvements.router import router as improvements_router
from app.integrations.router import router as integrations_router
from app.auth.router import router as auth_router
from app.prompts.router import router as prompts_router
from app.events.router import router as events_router
from app.knowledge.router import router as knowledge_router

# Import background workers — Phase 5: metrics aggregation + agent monitoring
from app.workers.metrics_calculator import run_metrics_calculator
from app.workers.heartbeat_monitor import run_monitor as run_heartbeat_monitor
from app.workers.integration_health_checker import run_health_checker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s", settings.app_name)

    # Spawn background workers as asyncio tasks.
    # They run concurrently with FastAPI's event loop — no threads needed.
    # On shutdown, we cancel them cleanly so no zombie tasks are left.
    worker_tasks = [
        asyncio.create_task(
            run_metrics_calculator(interval_seconds=3600),  # recalculate metrics every hour
            name="metrics_calculator",
        ),
        asyncio.create_task(
            run_heartbeat_monitor(interval=60),  # check agent heartbeats every minute
            name="heartbeat_monitor",
        ),
        asyncio.create_task(
            run_health_checker(interval=300),  # check integration health every 5 minutes
            name="integration_health_checker",
        ),
    ]
    logger.info("Started %d background workers", len(worker_tasks))

    yield  # Server is running

    # Graceful shutdown: cancel all workers and wait for them to finish
    for task in worker_tasks:
        task.cancel()
    await asyncio.gather(*worker_tasks, return_exceptions=True)
    logger.info("Shutting down %s — all workers stopped", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestTimingMiddleware)

prefix = settings.api_v1_prefix

# Auth-required dependency applied at router level — every endpoint under
# these routers will require a valid JWT Bearer token.
_auth = [Depends(get_current_user)]

# ─── Public routers (no auth required) ───
app.include_router(auth_router, prefix=f"{prefix}/auth", tags=["auth"])
app.include_router(events_router, prefix=f"{prefix}/events", tags=["events"])

# ─── Protected routers (JWT required) ───
app.include_router(agents_router, prefix=f"{prefix}/agents", tags=["agents"], dependencies=_auth)
app.include_router(departments_router, prefix=f"{prefix}/departments", tags=["departments"], dependencies=_auth)
app.include_router(tasks_router, prefix=f"{prefix}/tasks", tags=["tasks"], dependencies=_auth)
app.include_router(activities_router, prefix=f"{prefix}/activities", tags=["activities"], dependencies=_auth)
app.include_router(metrics_router, prefix=f"{prefix}/metrics", tags=["metrics"], dependencies=_auth)
app.include_router(interactions_router, prefix=f"{prefix}/interactions", tags=["interactions"], dependencies=_auth)
app.include_router(improvements_router, prefix=f"{prefix}/improvements", tags=["improvements"], dependencies=_auth)
app.include_router(integrations_router, prefix=f"{prefix}/integrations", tags=["integrations"], dependencies=_auth)
app.include_router(prompts_router, prefix=f"{prefix}/prompts", tags=["prompts"], dependencies=_auth)
app.include_router(knowledge_router, prefix=f"{prefix}/knowledge", tags=["knowledge"], dependencies=_auth)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "app": settings.app_name}
