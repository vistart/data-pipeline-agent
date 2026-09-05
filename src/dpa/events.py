"""Event sourcing for the data pipeline agent.

Records every operation (user messages, assistant responses, tool calls,
errors) with causal chain tracking. Events are stored in-memory and can
be exported to JSONL format.

Event structure::

    {
        "id": 1,
        "session_id": "abc123",
        "seq_num": 1,
        "event_type": "user_msg",
        "role": "user",
        "content": "Analyze orders.csv",
        "tool_name": null,
        "tool_args": null,
        "tool_result": null,
        "latency_ms": null,
        "created_at": "2025-..."
    }

Usage::

    from dpa.events import EventStore

    store = EventStore(session_id="abc123")
    store.user_message("Analyze orders.csv")
    store.tool_call("parse_data", {"source": "orders.csv"}, result, 42)
    store.assistant_message("I found 3 quality issues.")

    # Export to JSONL
    jsonl_str = store.to_jsonl()

    # Restore from JSONL
    restored = EventStore.from_jsonl(jsonl_str, "abc123")
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from dpa.models import OrderEvent


class EventStore:
    """In-memory event store with causal chain tracking.

    Maintains a sequence of events with monotonically increasing sequence
    numbers. Supports querying by event type, tool name, and causal chain.

    Args:
        session_id: The session this event store belongs to.
    """

    def __init__(self, session_id: str) -> None:
        """Initialize the event store for a session."""
        self.session_id = session_id
        self._seq = 0
        self._events: list[dict] = []

    def _now(self) -> str:
        """Return current UTC time in ISO 8601 format."""
        return datetime.now(timezone.utc).isoformat()

    def record(
        self,
        event_type: str,
        role: str,
        content: str | None = None,
        tool_name: str | None = None,
        tool_args: dict | None = None,
        tool_result: Any = None,
        latency_ms: int | None = None,
        token_input: int | None = None,
        token_output: int | None = None,
        causation_id: str | None = None,
        correlation_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        """Record an event with the given attributes.

        Args:
            event_type: Category of event (``"user_msg"``, ``"assistant_msg"``,
                ``"tool_call"``, ``"tool_result"``, ``"error"``).
            role: Actor role (``"user"``, ``"assistant"``, ``"tool"``, ``"system"``).
            content: Text content for message events.
            tool_name: Tool name for tool_call events.
            tool_args: Tool arguments for tool_call events.
            tool_result: Tool result for tool_call events.
            latency_ms: Execution time in milliseconds.
            token_input: Input token count.
            token_output: Output token count.
            causation_id: ID of the event that caused this event.
            correlation_id: ID linking related events.
            metadata: Additional metadata dict.

        Returns:
            The recorded event dict.
        """
        self._seq += 1
        event = {
            "id": self._seq,
            "session_id": self.session_id,
            "seq_num": self._seq,
            "event_type": event_type,
            "role": role,
            "content": content,
            "tool_name": tool_name,
            "tool_args": tool_args,
            "tool_result": tool_result,
            "latency_ms": latency_ms,
            "token_input": token_input,
            "token_output": token_output,
            "causation_id": causation_id,
            "correlation_id": correlation_id,
            "metadata": metadata,
            "created_at": self._now(),
        }
        self._events.append(event)
        return event

    def user_message(self, content: str) -> dict:
        """Record a user message event.

        Args:
            content: The user's message text.

        Returns:
            The recorded event dict.
        """
        return self.record("user_msg", "user", content=content)

    def assistant_message(self, content: str) -> dict:
        """Record an assistant response event.

        Args:
            content: The assistant's response text.

        Returns:
            The recorded event dict.
        """
        return self.record("assistant_msg", "assistant", content=content)

    def tool_call(self, name: str, args: dict, result: Any, latency_ms: int) -> dict:
        """Record a tool invocation event.

        Args:
            name: Tool name (e.g. ``"parse_data"``).
            args: Tool arguments.
            result: Tool execution result.
            latency_ms: Execution time in milliseconds.

        Returns:
            The recorded event dict.
        """
        return self.record(
            "tool_call",
            "tool",
            tool_name=name,
            tool_args=args,
            tool_result=result,
            latency_ms=latency_ms,
        )

    def error(self, message: str) -> dict:
        """Record an error event.

        Args:
            message: Error description text.

        Returns:
            The recorded event dict.
        """
        return self.record("error", "system", content=message)

    def get_events(self) -> list[dict]:
        """Return all recorded events.

        Returns:
            List of event dicts in recording order.
        """
        return self._events

    def get_causal_chain(self, event_id: int) -> list[dict]:
        """Return all events up to and including the given event ID.

        Useful for reconstructing the state at a specific point in time.

        Args:
            event_id: The event ID to trace back from.

        Returns:
            List of event dicts forming the causal chain.
        """
        chain = []
        for event in self._events:
            if event["id"] <= event_id:
                chain.append(event)
        return chain

    def get_tool_calls(self, tool_name: str | None = None) -> list[dict]:
        """Return all tool call events, optionally filtered by tool name.

        Args:
            tool_name: If provided, only return calls to this tool.

        Returns:
            List of tool call event dicts.
        """
        events = [e for e in self._events if e["event_type"] == "tool_call"]
        if tool_name:
            events = [e for e in events if e["tool_name"] == tool_name]
        return events

    def to_jsonl(self) -> str:
        """Export all events as a JSONL string.

        Returns:
            One JSON object per line, suitable for file storage or streaming.
        """
        lines = []
        for event in self._events:
            lines.append(json.dumps(event, ensure_ascii=False, default=str))
        return "\n".join(lines)

    @classmethod
    def from_jsonl(cls, jsonl_str: str, session_id: str) -> EventStore:
        """Restore an event store from a JSONL string.

        Args:
            jsonl_str: JSONL-formatted string (one event per line).
            session_id: The session ID for the restored store.

        Returns:
            A new EventStore populated with the parsed events.
        """
        store = cls(session_id)
        for line in jsonl_str.strip().split("\n"):
            if line.strip():
                event = json.loads(line)
                store._events.append(event)
                store._seq = max(store._seq, event.get("id", 0))
        return store
