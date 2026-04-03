import time
from datetime import datetime, timezone

import httpx

from .base import AgentState, BaseAdapter, HealthStatus, NormalizedEvent, TaskResult


class N8nAdapter(BaseAdapter):
    """Adapter for n8n workflow automation platform."""

    platform_name = "n8n"

    async def normalize_inbound(self, raw_payload: dict) -> NormalizedEvent:
        """Parse n8n webhook payloads including execution data and workflow info."""
        execution_id = raw_payload.get("executionId")
        workflow_id = raw_payload.get("workflowId")
        workflow_name = raw_payload.get("workflowName")

        # n8n wraps data differently based on webhook config
        data = raw_payload.get("data", raw_payload)

        # Determine event type from n8n execution status
        status = data.get("status", "").lower()
        event_type_map = {
            "success": "activity.completed",
            "error": "error",
            "running": "task.status_changed",
            "waiting": "task.status_changed",
        }
        event_type = event_type_map.get(status, data.get("event_type", "activity.completed"))

        return NormalizedEvent(
            event_type=event_type,
            agent_id=data.get("agent_id", ""),
            timestamp=datetime.now(timezone.utc),
            action=data.get("action", f"n8n execution {execution_id}"),
            task_id=data.get("task_id"),
            result=data.get("result"),
            metrics={
                "n8n_execution_id": execution_id,
                "n8n_workflow_id": workflow_id,
                "n8n_workflow_name": workflow_name,
                "n8n_status": status or None,
                **(data.get("metrics", {})),
            },
            raw_payload=raw_payload,
        )

    async def send_task(self, endpoint_url: str, task_data: dict, config: dict) -> TaskResult:
        """Trigger n8n workflow via webhook URL."""
        headers = {}
        # n8n webhook auth header if configured
        if config.get("webhook_auth_header"):
            headers[config["webhook_auth_header"]] = config.get("webhook_auth_value", "")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(endpoint_url, json=task_data, headers=headers)
                if resp.status_code < 400:
                    try:
                        data = resp.json()
                    except Exception:
                        data = {"raw": resp.text[:500]}
                    return TaskResult(
                        success=True,
                        message=f"n8n workflow triggered (HTTP {resp.status_code})",
                        external_id=data.get("executionId") or data.get("id"),
                        response_data=data,
                    )
                return TaskResult(
                    success=False,
                    message=f"n8n returned HTTP {resp.status_code}: {resp.text[:200]}",
                )
        except httpx.TimeoutException:
            return TaskResult(success=False, message="n8n webhook timed out")
        except Exception as e:
            return TaskResult(success=False, message=f"n8n request failed: {e}")

    async def check_health(self, endpoint_url: str, config: dict) -> HealthStatus:
        """Ping n8n instance health endpoint or webhook URL."""
        # Prefer the n8n API health endpoint if configured
        health_url = config.get("health_url") or endpoint_url
        try:
            start = time.perf_counter()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(health_url)
                latency = int((time.perf_counter() - start) * 1000)
                return HealthStatus(
                    healthy=resp.status_code < 500,
                    message=f"n8n responded with {resp.status_code}",
                    latency_ms=latency,
                )
        except httpx.TimeoutException:
            return HealthStatus(healthy=False, message="n8n health check timed out")
        except Exception as e:
            return HealthStatus(healthy=False, message=f"n8n unreachable: {e}")

    async def get_status(self, endpoint_url: str, config: dict) -> str:
        """Check n8n instance status via API if available."""
        api_url = config.get("api_url")
        if not api_url:
            return await super().get_status(endpoint_url, config)

        try:
            headers = {}
            if config.get("api_key"):
                headers["X-N8N-API-KEY"] = config["api_key"]
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{api_url}/healthz", headers=headers)
                if resp.status_code < 400:
                    return "active"
                return "error"
        except Exception:
            return "error"

    async def sync_agent_state(self, endpoint_url: str, config: dict) -> AgentState:
        """Sync state from n8n by checking active executions."""
        status = await self.get_status(endpoint_url, config)
        metadata: dict = {}

        api_url = config.get("api_url")
        if api_url and config.get("api_key"):
            try:
                headers = {"X-N8N-API-KEY": config["api_key"]}
                async with httpx.AsyncClient(timeout=10) as client:
                    resp = await client.get(
                        f"{api_url}/executions",
                        params={"status": "running", "limit": 5},
                        headers=headers,
                    )
                    if resp.status_code < 400:
                        data = resp.json()
                        running = data.get("data", [])
                        metadata["running_executions"] = len(running)
                        if running:
                            status = "busy"
            except Exception:
                pass

        return AgentState(status=status, metadata=metadata)
