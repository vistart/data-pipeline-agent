"""Metrics collection and exposure for the data pipeline agent.

Provides a lightweight in-memory metrics collector with Counter, Gauge,
Histogram, and Timer primitives. No external dependencies required.

Metrics are stored in-memory and can be exported via:
    - ``snapshot()``: Return all metrics as a dict
    - ``export_jsonl()``: Append to a JSONL file
    - CLI ``dpa metrics``: Display in table/JSON/JSONL format

Tracked metrics:
    - ``messages_total``: Total user messages received
    - ``tool_calls_total``: Total tool invocations
    - ``tool_calls_{name}``: Per-tool invocation count
    - ``tool_calls_success/error``: Tool success/failure counts
    - ``tool_latency_ms``: Tool execution latency histogram
    - ``llm_calls_total``: Total LLM API calls
    - ``llm_calls_success/error``: LLM success/failure counts
    - ``llm_latency_ms``: LLM response latency histogram
    - ``llm_tokens_input/output``: Token usage histograms
    - ``sessions_total``: Total sessions processed

Usage::

    from dpa.metrics import get_metrics

    m = get_metrics()
    m.inc("messages_total")
    m.start("llm_call")
    # ... call LLM ...
    m.stop("llm_call")
    print(m.snapshot())
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class MetricsCollector:
    """Lightweight in-memory metrics collector.

    Supports four metric types:
        - **Counter**: Monotonically increasing integer (e.g. total calls)
        - **Gauge**: Single floating-point value (e.g. current queue depth)
        - **Histogram**: Distribution of observed values (e.g. latencies)
        - **Timer**: Start/stop pairs that record elapsed time as histogram
    """

    def __init__(self) -> None:
        """Initialize the collector with empty metric stores."""
        self._counters: dict[str, int] = defaultdict(int)
        self._gauges: dict[str, float] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)
        self._timers: dict[str, float] = {}
        self._start_time = time.monotonic()

    # --- Counter ---

    def inc(self, name: str, value: int = 1) -> None:
        """Increment a counter by the given value.

        Args:
            name: Counter name (e.g. ``"tool_calls_total"``).
            value: Amount to increment (default 1).
        """
        self._counters[name] += value

    def get_counter(self, name: str) -> int:
        """Return the current value of a counter.

        Args:
            name: Counter name.

        Returns:
            Current counter value, or 0 if not set.
        """
        return self._counters.get(name, 0)

    # --- Gauge ---

    def set(self, name: str, value: float) -> None:
        """Set a gauge to the given value.

        Args:
            name: Gauge name.
            value: New gauge value.
        """
        self._gauges[name] = value

    def get_gauge(self, name: str) -> float | None:
        """Return the current value of a gauge.

        Args:
            name: Gauge name.

        Returns:
            Current gauge value, or None if not set.
        """
        return self._gauges.get(name)

    # --- Histogram ---

    def observe(self, name: str, value: float) -> None:
        """Record a value in a histogram.

        Args:
            name: Histogram name (e.g. ``"tool_latency_ms"``).
            value: Observed value to record.
        """
        self._histograms[name].append(value)

    def get_histogram(self, name: str) -> dict[str, float]:
        """Return statistics for a histogram.

        Args:
            name: Histogram name.

        Returns:
            Dict with keys: ``count``, ``min``, ``max``, ``avg``,
            ``p50``, ``p95``, ``p99``. Returns zeros if no observations.
        """
        values = self._histograms.get(name, [])
        if not values:
            return {"count": 0, "min": 0, "max": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        return {
            "count": n,
            "min": sorted_vals[0],
            "max": sorted_vals[-1],
            "avg": sum(sorted_vals) / n,
            "p50": sorted_vals[int(n * 0.5)],
            "p95": sorted_vals[min(int(n * 0.95), n - 1)],
            "p99": sorted_vals[min(int(n * 0.99), n - 1)],
        }

    # --- Timer ---

    def start(self, name: str) -> None:
        """Start a named timer.

        Args:
            name: Timer name (e.g. ``"llm_call"``). The elapsed time will
                be recorded to ``{name}_ms`` histogram when ``stop()`` is called.
        """
        self._timers[name] = time.monotonic()

    def stop(self, name: str) -> float:
        """Stop a named timer and record elapsed time.

        Args:
            name: Timer name (must match a prior ``start()`` call).

        Returns:
            Elapsed time in milliseconds, or 0 if timer was not started.
        """
        start = self._timers.pop(name, None)
        if start is None:
            return 0
        elapsed = (time.monotonic() - start) * 1000  # ms
        self.observe(f"{name}_ms", elapsed)
        return elapsed

    # --- Convenience ---

    def record_tool_call(self, tool_name: str, latency_ms: int, success: bool) -> None:
        """Record metrics for a tool invocation.

        Increments ``tool_calls_total``, per-tool counter, success/error
        counters, and records latency histograms.

        Args:
            tool_name: Name of the tool that was called.
            latency_ms: Execution time in milliseconds.
            success: Whether the tool call succeeded.
        """
        self.inc("tool_calls_total")
        self.inc(f"tool_calls_{tool_name}")
        if success:
            self.inc("tool_calls_success")
        else:
            self.inc("tool_calls_error")
        self.observe("tool_latency_ms", latency_ms)
        self.observe(f"tool_latency_{tool_name}_ms", latency_ms)

    def record_llm_call(self, model: str, latency_ms: int, token_input: int, token_output: int, success: bool) -> None:
        """Record metrics for an LLM API call.

        Increments ``llm_calls_total``, success/error counters, records
        latency and token usage histograms, and accumulates total token
        counters.

        Args:
            model: LLM model name used.
            latency_ms: Response time in milliseconds.
            token_input: Number of input tokens.
            token_output: Number of output tokens.
            success: Whether the API call succeeded.
        """
        self.inc("llm_calls_total")
        if success:
            self.inc("llm_calls_success")
        else:
            self.inc("llm_calls_error")
        self.observe("llm_latency_ms", latency_ms)
        self.observe("llm_token_input", token_input)
        self.observe("llm_token_output", token_output)
        self.inc("llm_tokens_input_total", token_input)
        self.inc("llm_tokens_output_total", token_output)

    def record_session(self, tool_calls: int, llm_calls: int, duration_ms: float) -> None:
        """Record metrics for a completed session.

        Args:
            tool_calls: Total tool calls in the session.
            llm_calls: Total LLM calls in the session.
            duration_ms: Total session duration in milliseconds.
        """
        self.inc("sessions_total")
        self.observe("session_tool_calls", tool_calls)
        self.observe("session_llm_calls", llm_calls)
        self.observe("session_duration_ms", duration_ms)

    # --- Export ---

    def snapshot(self) -> dict[str, Any]:
        """Export all metrics as a snapshot dict.

        Returns:
            Dict with keys: ``timestamp``, ``uptime_seconds``,
            ``counters``, ``gauges``, ``histograms``.
        """
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": time.monotonic() - self._start_time,
            "counters": dict(self._counters),
            "gauges": dict(self._gauges),
            "histograms": {name: self.get_histogram(name) for name in self._histograms},
        }

    def export_jsonl(self, path: str | Path) -> None:
        """Append a metrics snapshot to a JSONL file.

        Args:
            path: File path to append to (created if needed).
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = self.snapshot()
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(snapshot, ensure_ascii=False, default=str) + "\n")

    def reset(self) -> None:
        """Reset all metrics to their initial state."""
        self._counters.clear()
        self._gauges.clear()
        self._histograms.clear()
        self._timers.clear()
        self._start_time = time.monotonic()


# Global singleton instance
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """Return the global MetricsCollector singleton."""
    return _metrics
