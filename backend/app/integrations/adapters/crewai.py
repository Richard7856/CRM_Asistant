import time
from datetime import datetime, timezone

import httpx

from .base import AgentState, BaseAdapter, HealthStatus, NormalizedEvent, TaskResult


class CrewAIAdapter(BaseAdapter):
    """Adapter for CrewAI crew endpoints."""

    platform_name = "crewai"

    async def normalize_inbound(self, raw_payload: dict) -> NormalizedEvent:
        """Parse CrewAI execution results."""
        crew_id = raw_payload.get("crew_id")
        kickoff_id = raw_payload.get("kickoff_id") or raw_payload.get("execution_id")

        # CrewAI status mapping
        status = raw_payload.get("status", "").lower()
        event_type_map = {
            "completed": "activity.completed",
            "success": "activity.completed",
            "failed": "error",
            "error": "error",
            "running": "task.status_changed",
            "started": "task.status_changed",
        }
        event_type = event_type_map.get(status, raw_payload.get("event_type", "activity.completed"))

        # Extract crew output
        result = raw_payload.get("result") or raw_payload.get("output")
        if isinstance(result, str):
            result = {"output": result}

        return NormalizedEvent(
            event_type=event_type,
            agent_id=raw_payload.get("agent_id", ""),
            timestamp=datetime.now(timezone.utc),
            action=raw_payload.get("action", f"crewai kickoff {kickoff_id}"),
            task_id=raw_payload.get("task_id"),
            result=result,
            metrics={
                "crewai_crew_id": crew_id,
                "crewai_kickoff_id": kickoff_id,
                "crewai_status": status or None,
                "tasks_completed": raw_payload.get("tasks_completed"),
                "agents_involved": raw_payload.get("agents_involved"),
                **(raw_payload.get("metrics", {})),
            },
            raw_payload=raw_payload,
        )

    async def send_task(self, endpoint_url: str, task_data: dict, config: dict) -> TaskResult:
        """POST to CrewAI kickoff endpoint to start a crew execution."""
        url = endpoint_url.rstrip("/")
        kickoff_path = config.get("kickoff_path", "/kickoff")
        full_url = f"{url}{kickoff_path}"

        # CrewAI expects inputs for the crew
        payload = {
            "inputs": task_data.get("inputs", task_data),
        }
        # Add crew config overrides if specified
        if config.get("crew_config"):
            payload["config"] = config["crew_config"]

        headers = {"Content-Type": "application/json"}
        if config.get("api_key"):
            headers["Authorization"] = f"Bearer {config['api_key']}"

        try:
            async with httpx.AsyncClient(timeout=config.get("timeout", 120)) as client:
                resp = await client.post(full_url, json=payload, headers=headers)
                if resp.status_code < 400:
                    try:
                        data = resp.json()
                    except Exception:
                        data = {"raw": resp.text[:500]}
                    return TaskResult(
                        success=True,
                        message=f"CrewAI kickoff started (HTTP {resp.status_code})",
                        external_id=data.get("kickoff_id") or data.get("id"),
                        response_data=data,
                    )
                return TaskResult(
                    success=False,
                    message=f"CrewAI returned HTTP {resp.status_code}: {resp.text[:200]}",
                )
        except httpx.TimeoutException:
            return TaskResult(success=False, message="CrewAI kickoff timed out")
        except Exception as e:
            return TaskResult(success=False, message=f"CrewAI request failed: {e}")

    async def check_health(self, endpoint_url: str, config: dict) -> HealthStatus:
        """Ping CrewAI crew status endpoint."""
        url = endpoint_url.rstrip("/")
        health_path = config.get("health_path", "/status")
        health_url = config.get("health_url", f"{url}{health_path}")

        headers = {}
        if config.get("api_key"):
            headers["Authorization"] = f"Bearer {config['api_key']}"

        try:
            start = time.perf_counter()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(health_url, headers=headers)
                latency = int((time.perf_counter() - start) * 1000)
                return HealthStatus(
                    healthy=resp.status_code < 400,
                    message=f"CrewAI responded with {resp.status_code}",
                    latency_ms=latency,
                )
        except httpx.TimeoutException:
            return HealthStatus(healthy=False, message="CrewAI health check timed out")
        except Exception as e:
            return HealthStatus(healthy=False, message=f"CrewAI unreachable: {e}")

    async def get_status(self, endpoint_url: str, config: dict) -> str:
        """Get CrewAI crew status."""
        url = endpoint_url.rstrip("/")
        status_path = config.get("status_path", "/status")

        headers = {}
        if config.get("api_key"):
            headers["Authorization"] = f"Bearer {config['api_key']}"

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{url}{status_path}", headers=headers)
                if resp.status_code < 400:
                    data = resp.json()
                    crew_status = data.get("status", "active")
                    status_map = {
                        "ready": "idle",
                        "running": "busy",
                        "error": "error",
                        "idle": "idle",
                    }
                    return status_map.get(crew_status, "active")
                return "error"
        except Exception:
            return "error"

    async def sync_agent_state(self, endpoint_url: str, config: dict) -> AgentState:
        """Sync CrewAI crew state including active executions."""
        status = await self.get_status(endpoint_url, config)
        metadata: dict = {}

        url = endpoint_url.rstrip("/")
        headers = {}
        if config.get("api_key"):
            headers["Authorization"] = f"Bearer {config['api_key']}"

        # Try to fetch crew info
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{url}/info", headers=headers)
                if resp.status_code < 400:
                    metadata["crew_info"] = resp.json()
        except Exception:
            pass

        current_task = None
        if status == "busy":
            current_task = metadata.get("crew_info", {}).get("current_task")

        return AgentState(status=status, current_task=current_task, metadata=metadata)
