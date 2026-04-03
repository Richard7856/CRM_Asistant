/**
 * SSE hook — connects to the backend event stream and auto-invalidates
 * TanStack Query caches when tasks/agents change.
 *
 * Usage: call useEventStream() once in a top-level layout component.
 * It manages reconnection automatically.
 */

import { useEffect, useRef, useCallback } from "react";
import { useQueryClient } from "@tanstack/react-query";

interface SSEEvent {
  type: string;
  data: Record<string, unknown>;
  timestamp: string;
}

// Maps SSE event types to the query keys that should be invalidated.
// metric.updated fires after the hourly background worker recalculates —
// we refresh metrics + agents so KPIs and leaderboard stay current.
const EVENT_INVALIDATION_MAP: Record<string, string[][]> = {
  "task.started": [["tasks"], ["activities"], ["metrics"]],
  "task.completed": [["tasks"], ["activities"], ["metrics"], ["agents"]],
  "task.failed": [["tasks"], ["activities"], ["metrics"], ["agents"]],
  "task.dispatched": [["tasks"], ["activities"]],
  "agent.status_changed": [["agents"], ["metrics"]],
  "metric.updated": [["metrics"], ["agents"]],
};

export function useEventStream(
  onEvent?: (event: SSEEvent) => void,
) {
  const queryClient = useQueryClient();
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const connect = useCallback(() => {
    // Close existing connection if any
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
    }

    const url = "/api/v1/events/stream";
    const es = new EventSource(url);
    eventSourceRef.current = es;

    // Listen for all event types we care about
    const eventTypes = [
      "connected",
      "task.started",
      "task.completed",
      "task.failed",
      "task.dispatched",
      "agent.status_changed",
      "metric.updated",  // fired by the hourly metrics calculator worker
    ];

    for (const eventType of eventTypes) {
      es.addEventListener(eventType, (e: MessageEvent) => {
        try {
          const parsed: SSEEvent = JSON.parse(e.data);

          // Invalidate relevant query caches
          const keysToInvalidate = EVENT_INVALIDATION_MAP[parsed.type] || [];
          for (const queryKey of keysToInvalidate) {
            queryClient.invalidateQueries({ queryKey });
          }

          // Call optional callback for UI notifications (toasts, etc.)
          onEvent?.(parsed);
        } catch {
          console.warn("Failed to parse SSE event:", e.data);
        }
      });
    }

    es.onerror = () => {
      es.close();
      // Reconnect after 3 seconds — exponential backoff not needed for MVP
      reconnectTimeoutRef.current = setTimeout(() => {
        console.info("SSE reconnecting...");
        connect();
      }, 3000);
    };
  }, [queryClient, onEvent]);

  useEffect(() => {
    connect();

    return () => {
      eventSourceRef.current?.close();
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect]);
}
