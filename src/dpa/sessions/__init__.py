"""Session persistence via JSONL files.

Each session is stored as a JSONL file (one JSON object per line) in the
``sessions/`` directory. Files are named ``{date}_{session_id}.jsonl``.

Session log entries have the following structure::

    {"role": "user", "ts": "2025-...", "content": "Analyze orders.csv"}
    {"role": "assistant", "ts": "2025-...", "content": "I'll parse the file..."}
    {"role": "tool_call", "ts": "2025-...", "tool": "parse_data",
     "args": {"source": "orders.csv"}, "result": {...}, "latency_ms": 42}
    {"role": "error", "ts": "2025-...", "content": "File not found"}

Usage::

    from dpa.sessions import Session

    session = Session(name="demo")
    session.user("Parse orders.csv")
    session.assistant("I'll parse that for you.")
    session.tool_call("parse_data", {"source": "orders.csv"}, result, 42)

    # Later, load and replay
    msgs = session.messages()
    s2 = Session.load(session.path)
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SESSIONS_DIR = Path("sessions")


def _now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


class Session:
    """Manages a single conversation session with JSONL persistence.

    Each session gets a unique ID and writes all messages to a JSONL file.
    Supports incremental appending (no file rewrite needed).

    Args:
        session_id (str, optional): Unique session identifier. Auto-generated
            if not provided.
        name (str, optional): Human-readable session name (e.g. scenario name).
    """

    def __init__(self, session_id: str | None = None, name: str = "") -> None:
        """Initialize a session, creating the JSONL file if needed."""
        self.session_id = session_id or uuid.uuid4().hex[:12]
        self.name = name
        self.created_at = _now_iso()
        self._path = SESSIONS_DIR / f"{self.created_at[:10]}_{self.session_id}.jsonl"
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

    def log(self, role: str, **kwargs: Any) -> None:
        """Append a log entry to the session file.

        Args:
            role: The message role (``"user"``, ``"assistant"``, ``"tool_call"``,
                ``"error"``).
            **kwargs: Additional fields (``content``, ``tool``, ``args``, etc.).
        """
        entry = {"role": role, "ts": _now_iso(), **kwargs}
        with open(self._path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def user(self, content: str) -> None:
        """Log a user message.

        Args:
            content: The user's message text.
        """
        self.log("user", content=content)

    def assistant(self, content: str) -> None:
        """Log an assistant response.

        Args:
            content: The assistant's response text.
        """
        self.log("assistant", content=content)

    def tool_call(self, name: str, args: dict, result: Any, latency_ms: int) -> None:
        """Log a tool execution record.

        Args:
            name: Tool name (e.g. ``"parse_data"``).
            args: Tool arguments passed by the LLM.
            result: Tool execution result dict.
            latency_ms: Execution time in milliseconds.
        """
        self.log("tool_call", tool=name, args=args, result=result, latency_ms=latency_ms)

    def error(self, message: str) -> None:
        """Log an error message.

        Args:
            message: Error description text.
        """
        self.log("error", content=message)

    @property
    def path(self) -> Path:
        """Return the path to this session's JSONL file."""
        return self._path

    def messages(self) -> list[dict]:
        """Load all log entries from the session file.

        Returns:
            List of dicts, one per line in the JSONL file. Returns empty
            list if the file does not exist.
        """
        if not self._path.exists():
            return []
        with open(self._path, encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    @classmethod
    def load(cls, path: Path) -> Session:
        """Load an existing session from a JSONL file.

        Args:
            path: Path to the session JSONL file.

        Returns:
            A Session instance with the loaded file path and ID.
        """
        s = cls.__new__(cls)
        s._path = path
        s.session_id = path.stem.split("_", 1)[-1]
        s.name = ""
        s.created_at = ""
        return s
