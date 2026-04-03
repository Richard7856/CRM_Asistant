"""
SSE (Server-Sent Events) endpoint for real-time dashboard updates.

The client connects once via EventSource and receives a continuous
stream of events: task completions, agent status changes, etc.
"""

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.events import Event, event_bus

logger = logging.getLogger(__name__)
router = APIRouter()


async def _event_generator(sub_id: str, queue: asyncio.Queue):
    """Yield SSE-formatted events from the subscriber queue."""
    try:
        # Send initial connection event so the client knows it's live
        welcome = Event(
            type="connected",
            data={"message": "SSE stream active", "subscriber_id": sub_id},
        )
        yield welcome.to_sse()

        while True:
            try:
                # Wait up to 30s for an event, then send keepalive
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield event.to_sse()
            except asyncio.TimeoutError:
                # SSE keepalive — prevents proxy/browser from closing the connection
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        event_bus.unsubscribe(sub_id)


@router.get("/stream")
async def event_stream():
    """
    SSE endpoint — connect via EventSource to get real-time updates.

    Events include:
    - task.started, task.completed, task.failed, task.dispatched
    - agent.status_changed
    - connected (initial handshake)
    """
    sub_id, queue = event_bus.subscribe()

    return StreamingResponse(
        _event_generator(sub_id, queue),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering if proxied
        },
    )


@router.get("/subscribers")
async def get_subscriber_count():
    """Check how many SSE clients are connected."""
    return {"subscribers": event_bus.subscriber_count}
