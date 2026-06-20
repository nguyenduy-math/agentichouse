"""
Per-request pipeline progress tracker for SSE streaming.

Each chat turn gets its own ProgressTracker stored in app.state.progress_store.
The orchestrator calls .emit() at each pipeline stage; the SSE endpoint streams
those events to the browser via GET /api/v1/chat/{session_id}/progress.

Event shapes (all serialised as JSON in the SSE data field):
  {"type": "step",       "step": "rewrite"|"retrieve"|"synthesize"|"verify"}
  {"type": "classified", "domains": [...], "mode": "local"|"global"}
  {"type": "agent_start","domain": "hr"}
  {"type": "agent_done", "domain": "hr"}
  {"type": "done"}
  {"type": "error",      "message": "..."}
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncGenerator


class ProgressTracker:
    """
    Holds the ordered list of pipeline events for one chat turn.

    Thread/coroutine safety:
      - emit() appends to a plain list and sets an asyncio.Event — safe to call
        from any coroutine in the same event loop.
      - stream() is an async generator; multiple concurrent SSE clients are
        supported (each has its own cursor).
    """

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._event = asyncio.Event()
        self._done = False

    def emit(self, event_type: str, **data: Any) -> None:
        """Append an event and wake up any waiting SSE subscribers."""
        self._events.append({"type": event_type, **data})
        self._event.set()
        if event_type in ("done", "error"):
            self._done = True

    async def stream(self, offset: int = 0) -> AsyncGenerator[str, None]:
        """
        Async generator yielding SSE-formatted chunks.

        Drains buffered events from `offset` immediately, then waits for new
        ones. Closes after the 'done' or 'error' event has been sent.
        """
        cursor = offset
        while True:
            # Drain available events
            while cursor < len(self._events):
                payload = json.dumps(self._events[cursor], ensure_ascii=False)
                yield f"data: {payload}\n\n"
                cursor += 1

            if self._done and cursor >= len(self._events):
                break

            # Clear-before-wait to avoid missing a wakeup
            self._event.clear()
            if cursor < len(self._events):
                continue

            try:
                await asyncio.wait_for(self._event.wait(), timeout=120.0)
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
