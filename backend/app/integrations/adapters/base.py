from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class NormalizedEvent:
    """Standardized event format from any external platform."""
    event_type: str  # activity.completed, task.status_changed, heartbeat, error
    agent_id: str
    timestamp: datetime
    action: str | None = None
    task_id: str | None = None
    result: dict | None = None
    metrics: dict | None = None
    raw_payload: dict | None = None


@dataclass
class HealthStatus:
    healthy: bool
    message: str
    latency_ms: int | None = None


@dataclass
class TaskResult:
    """Result of dispatching a task to an external platform."""
    success: bool
    message: str
    external_id: str | None = None
    response_data: dict | None = None


@dataclass
class AgentState:
    """Synchronized state from an external agent platform."""
    status: str  # active, idle, busy, error, offline
    current_task: str | None = None
    metadata: dict = field(default_factory=dict)


class BaseAdapter(ABC):
    """Abstract base class for platform-specific integrations."""

    platform_name: str = "generic"

    @abstractmethod
    async def normalize_inbound(self, raw_payload: dict) -> NormalizedEvent:
        """Convert platform-specific webhook payload to normalized format."""
        ...

    @abstractmethod
    async def send_task(self, endpoint_url: str, task_data: dict, config: dict) -> TaskResult:
        """Push a task to the external agent. Returns TaskResult."""
        ...

    @abstractmethod
    async def check_health(self, endpoint_url: str, config: dict) -> HealthStatus:
        """Ping the external agent to verify connectivity."""
        ...

    async def get_status(self, endpoint_url: str, config: dict) -> str:
        """Get the current status of the external agent. Defaults to health-based check."""
        health = await self.check_health(endpoint_url, config)
        return "active" if health.healthy else "error"

    async def sync_agent_state(self, endpoint_url: str, config: dict) -> AgentState:
        """Sync full agent state from the external platform. Defaults to status-only."""
        status = await self.get_status(endpoint_url, config)
        return AgentState(status=status)


class AdapterRegistry:
    """Maps platform names to adapter classes."""

    _adapters: dict[str, type[BaseAdapter]] = {}

    @classmethod
    def register(cls, platform: str, adapter_cls: type[BaseAdapter]) -> None:
        cls._adapters[platform.lower()] = adapter_cls

    @classmethod
    def get(cls, platform: str) -> BaseAdapter:
        """Return an instance of the adapter for the given platform."""
        adapter_cls = cls._adapters.get(platform.lower())
        if adapter_cls is None:
            # Fall back to generic
            from app.integrations.adapters.generic import GenericAdapter
            return GenericAdapter()
        return adapter_cls()

    @classmethod
    def supported_platforms(cls) -> list[str]:
        return list(cls._adapters.keys())

    @classmethod
    def has(cls, platform: str) -> bool:
        return platform.lower() in cls._adapters
