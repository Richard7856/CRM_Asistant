import time
from datetime import datetime, timezone

import httpx

from .base import AgentState, BaseAdapter, HealthStatus, NormalizedEvent, TaskResult


class GenericAdapter(BaseAdapter):
    """Adapter for any platform following the standard CRM Agents protocol."""

    platform_name = "generic"

    async def normalize_inbound(self, raw_payload: dict) -> NormalizedEvent:
        payload = raw_payload.get("payload", {})
        return NormalizedEvent(
            event_type=raw_payload.get("event_type", "activity.completed"),
            agent_id=raw_payload.get("agent_id", ""),
            timestamp=datetime.fromisoformat(
                raw_payload.get("timestamp", datetime.now(timezone.utc).isoformat())
            ),
            action=payload.get("action"),
            task_id=payload.get("task_id"),
            result=payload.get("result"),
            metrics=payload.get("metrics"),
            raw_payload=raw_payload,
        )

    async def send_task(self, endpoint_url: str, task_data: dict, config: dict) -> TaskResult:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(endpoint_url, json=task_data)
                if resp.status_code < 400:
                    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
                    return TaskResult(
                        success=True,
                        message=f"Task dispatched (HTTP {resp.status_code})",
                        external_id=data.get("id") or data.get("task_id"),
                        response_data=data,
                    )
                return TaskResult(
                    success=False,
                    message=f"HTTP {resp.status_code}: {resp.text[:200]}",
                )
        except Exception as e:
            return TaskResult(success=False, message=f"Request failed: {e}")

    async def check_health(self, endpoint_url: str, config: dict) -> HealthStatus:
        try:
            start = time.perf_counter()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(endpoint_url)
                latency = int((time.perf_counter() - start) * 1000)
                return HealthStatus(
                    healthy=resp.status_code < 400,
                    message=f"Status {resp.status_code}",
                    latency_ms=latency,
                )
        except Exception as e:
            return HealthStatus(healthy=False, message=str(e))
