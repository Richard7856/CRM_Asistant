import time
from datetime import datetime, timezone

import httpx

from .base import AgentState, BaseAdapter, HealthStatus, NormalizedEvent, TaskResult


class LangChainAdapter(BaseAdapter):
    """Adapter for LangChain/LangServe endpoints."""

    platform_name = "langchain"

    async def normalize_inbound(self, raw_payload: dict) -> NormalizedEvent:
        """Parse LangServe response payloads."""
        # LangServe responses typically have output/input keys
        output = raw_payload.get("output", raw_payload.get("result"))
        run_id = raw_payload.get("run_id") or raw_payload.get("metadata", {}).get("run_id")

        # Determine event type
        status = raw_payload.get("status", "completed")
        event_type_map = {
            "completed": "activity.completed",
            "error": "error",
            "running": "task.status_changed",
        }
        event_type = event_type_map.get(status, raw_payload.get("event_type", "activity.completed"))

        return NormalizedEvent(
            event_type=event_type,
            agent_id=raw_payload.get("agent_id", ""),
            timestamp=datetime.now(timezone.utc),
            action=raw_payload.get("action", f"langchain run {run_id}"),
            task_id=raw_payload.get("task_id"),
            result={"output": output} if output else raw_payload.get("result"),
            metrics={
                "langserve_run_id": run_id,
                "model": raw_payload.get("metadata", {}).get("model"),
                "tokens_used": raw_payload.get("metadata", {}).get("tokens_used"),
                **(raw_payload.get("metrics", {})),
            },
            raw_payload=raw_payload,
        )

    async def send_task(self, endpoint_url: str, task_data: dict, config: dict) -> TaskResult:
        """POST to LangServe /invoke or /batch endpoint."""
        # Determine invoke mode: single or batch
        mode = config.get("mode", "invoke")  # invoke | batch
        url = endpoint_url.rstrip("/")

        # LangServe expects input wrapped in {"input": ...}
        if mode == "batch":
            url = f"{url}/batch"
            payload = {"inputs": task_data.get("inputs", [task_data])}
        else:
            url = f"{url}/invoke"
            payload = {"input": task_data.get("input", task_data)}

        # Add config if provided
        if config.get("langserve_config"):
            payload["config"] = config["langserve_config"]

        headers = {"Content-Type": "application/json"}
        if config.get("api_key"):
            headers["Authorization"] = f"Bearer {config['api_key']}"

        try:
            async with httpx.AsyncClient(timeout=config.get("timeout", 60)) as client:
                resp = await client.post(url, json=payload, headers=headers)
                if resp.status_code < 400:
                    data = resp.json()
                    return TaskResult(
                        success=True,
                        message=f"LangServe {mode} succeeded (HTTP {resp.status_code})",
                        external_id=data.get("run_id") or data.get("metadata", {}).get("run_id"),
                        response_data=data,
                    )
                return TaskResult(
                    success=False,
                    message=f"LangServe returned HTTP {resp.status_code}: {resp.text[:200]}",
                )
        except httpx.TimeoutException:
            return TaskResult(success=False, message="LangServe request timed out")
        except Exception as e:
            return TaskResult(success=False, message=f"LangServe request failed: {e}")

    async def check_health(self, endpoint_url: str, config: dict) -> HealthStatus:
        """Check LangServe health by hitting the root or /health endpoint."""
        url = endpoint_url.rstrip("/")
        # LangServe exposes playground + input/output schema at root
        health_url = config.get("health_url", url)

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
                    message=f"LangServe responded with {resp.status_code}",
                    latency_ms=latency,
                )
        except httpx.TimeoutException:
            return HealthStatus(healthy=False, message="LangServe health check timed out")
        except Exception as e:
            return HealthStatus(healthy=False, message=f"LangServe unreachable: {e}")

    async def get_status(self, endpoint_url: str, config: dict) -> str:
        """Determine status from health check."""
        health = await self.check_health(endpoint_url, config)
        return "active" if health.healthy else "error"

    async def sync_agent_state(self, endpoint_url: str, config: dict) -> AgentState:
        """Sync LangServe agent state. Fetches schema info if available."""
        status = await self.get_status(endpoint_url, config)
        metadata: dict = {}

        url = endpoint_url.rstrip("/")
        headers = {}
        if config.get("api_key"):
            headers["Authorization"] = f"Bearer {config['api_key']}"

        # Try to fetch input/output schema for metadata
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{url}/input_schema", headers=headers)
                if resp.status_code < 400:
                    metadata["input_schema"] = resp.json()
                resp = await client.get(f"{url}/output_schema", headers=headers)
                if resp.status_code < 400:
                    metadata["output_schema"] = resp.json()
        except Exception:
            pass

        return AgentState(status=status, metadata=metadata)
