import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.integrations.adapters import AdapterRegistry
from app.integrations.schemas import (
    BulkHealthResponse,
    IntegrationHealthResponse,
    IntegrationSyncResponse,
    PlatformConfigField,
    PlatformInfo,
    TaskDispatchRequest,
    TaskDispatchResponse,
    WebhookEventResponse,
)
from app.integrations.service import IntegrationService

router = APIRouter()


# ---------------------------------------------------------------------------
# Webhook inbound
# ---------------------------------------------------------------------------


@router.post("/webhook/{platform}", response_model=WebhookEventResponse)
async def receive_webhook(
    platform: str,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
):
    """Receive webhooks from external platforms (n8n, langchain, crewai, etc.)."""
    service = IntegrationService(db)
    result = service.process_webhook(platform, payload)
    # Handle both sync and async
    if hasattr(result, "__await__"):
        result = await result
    return WebhookEventResponse(**result)


# ---------------------------------------------------------------------------
# Task dispatch
# ---------------------------------------------------------------------------


@router.post("/dispatch/{agent_id}", response_model=TaskDispatchResponse)
async def dispatch_task(
    agent_id: uuid.UUID,
    request: TaskDispatchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Send a task to an external agent via its configured integration."""
    service = IntegrationService(db)
    task_data = {
        "task_type": request.task_type,
        "input_data": request.input_data,
        "priority": request.priority,
        "callback_url": request.callback_url,
    }
    if request.config_overrides:
        task_data["config_overrides"] = request.config_overrides

    result = await service.dispatch_task(agent_id, task_data)
    return TaskDispatchResponse(**result)


# ---------------------------------------------------------------------------
# Health checks
# ---------------------------------------------------------------------------


@router.get("/health/{agent_id}", response_model=IntegrationHealthResponse)
async def check_health(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Check the health of a single agent's external integration."""
    service = IntegrationService(db)
    result = await service.check_agent_health(agent_id)
    return IntegrationHealthResponse(**result)


@router.post("/health/check-all", response_model=BulkHealthResponse)
async def check_all_health(
    db: AsyncSession = Depends(get_db),
):
    """Check health of all active external integrations."""
    service = IntegrationService(db)
    result = await service.check_all_integrations_health()
    return BulkHealthResponse(**result)


# ---------------------------------------------------------------------------
# Sync
# ---------------------------------------------------------------------------


@router.post("/sync/{agent_id}", response_model=IntegrationSyncResponse)
async def sync_agent(
    agent_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Sync external agent state from its platform."""
    service = IntegrationService(db)
    result = await service.sync_agent(agent_id)
    return IntegrationSyncResponse(**result)


# ---------------------------------------------------------------------------
# Platform info
# ---------------------------------------------------------------------------


@router.get("/platforms", response_model=list[PlatformInfo])
async def list_platforms():
    """List supported integration platforms with their config schemas."""
    platforms = [
        PlatformInfo(
            name="n8n",
            description="n8n workflow automation platform",
            config_fields=[
                PlatformConfigField(name="health_url", type="string", description="Custom health check URL"),
                PlatformConfigField(name="api_url", type="string", description="n8n API base URL (e.g., http://localhost:5678/api/v1)"),
                PlatformConfigField(name="api_key", type="string", description="n8n API key for management operations"),
                PlatformConfigField(name="webhook_auth_header", type="string", description="Custom auth header name for webhooks"),
                PlatformConfigField(name="webhook_auth_value", type="string", description="Custom auth header value"),
            ],
        ),
        PlatformInfo(
            name="langchain",
            description="LangChain/LangServe agent endpoints",
            config_fields=[
                PlatformConfigField(name="mode", type="string", description="Invoke mode: 'invoke' or 'batch'"),
                PlatformConfigField(name="api_key", type="string", description="Bearer token for authentication"),
                PlatformConfigField(name="health_url", type="string", description="Custom health check URL"),
                PlatformConfigField(name="timeout", type="integer", description="Request timeout in seconds (default: 60)"),
                PlatformConfigField(name="langserve_config", type="object", description="LangServe config to pass with requests"),
            ],
        ),
        PlatformInfo(
            name="crewai",
            description="CrewAI crew execution endpoints",
            config_fields=[
                PlatformConfigField(name="kickoff_path", type="string", description="Kickoff endpoint path (default: /kickoff)"),
                PlatformConfigField(name="status_path", type="string", description="Status endpoint path (default: /status)"),
                PlatformConfigField(name="health_path", type="string", description="Health endpoint path (default: /status)"),
                PlatformConfigField(name="api_key", type="string", description="Bearer token for authentication"),
                PlatformConfigField(name="timeout", type="integer", description="Request timeout in seconds (default: 120)"),
                PlatformConfigField(name="crew_config", type="object", description="CrewAI config overrides"),
            ],
        ),
        PlatformInfo(
            name="generic",
            description="Generic HTTP endpoint following CRM Agents protocol",
            config_fields=[
                PlatformConfigField(name="health_url", type="string", description="Custom health check URL"),
            ],
        ),
    ]
    return platforms
