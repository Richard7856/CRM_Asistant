"""
In-memory event bus for Server-Sent Events (SSE).

Lightweight pub/sub: any part of the app can publish events,
and SSE connections consume them in real time.

Why in-memory instead of Redis: MVP scope — single process.
For multi-process production, swap this for Redis Pub/Sub.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """A single event to broadcast to SSE subscribers."""
    type: str                          # e.g. "task.completed", "agent.status_changed"
    data: dict[str, Any]               # payload
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_sse(self) -> str:
        """Format as SSE wire protocol."""
        payload = {"type": self.type, "data": self.data, "timestamp": self.timestamp}
        return f"id: {self.id}\nevent: {self.type}\ndata: {json.dumps(payload)}\n\n"


class EventBus:
    """
    Fan-out event bus: each SSE connection gets its own queue.
    publish() sends to ALL active subscribers.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, asyncio.Queue[Event]] = {}

    def subscribe(self) -> tuple[str, asyncio.Queue[Event]]:
        """Create a new subscriber queue. Returns (subscriber_id, queue)."""
        sub_id = str(uuid.uuid4())[:8]
        queue: asyncio.Queue[Event] = asyncio.Queue(maxsize=100)
        self._subscribers[sub_id] = queue
        logger.info("SSE subscriber %s connected (total: %d)", sub_id, len(self._subscribers))
        return sub_id, queue

    def unsubscribe(self, sub_id: str) -> None:
        """Remove a subscriber."""
        self._subscribers.pop(sub_id, None)
        logger.info("SSE subscriber %s disconnected (total: %d)", sub_id, len(self._subscribers))

    async def publish(self, event: Event) -> None:
        """Broadcast event to all subscribers. Drops if a queue is full."""
        dead = []
        for sub_id, queue in self._subscribers.items():
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer — drop event to avoid backpressure
                logger.warning("SSE queue full for subscriber %s, dropping event", sub_id)
                dead.append(sub_id)

        # Clean up dead subscribers
        for sub_id in dead:
            self._subscribers.pop(sub_id, None)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


# Global singleton — imported wherever events need to be published or consumed
event_bus = EventBus()
