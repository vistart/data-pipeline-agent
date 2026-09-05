"""Database models for the data pipeline agent.

Defines ActiveRecord models for quarantine records, event sourcing, and
schema baseline management. These models use rhosocial-activerecord's
type-safe field definitions with ``UseSqlType`` and backend-specific types.

Usage::

    from dpa.models import QuarantineRecord, OrderEvent, SchemaBaseline

    # Create a quarantine record
    record = QuarantineRecord(
        id=0,  # auto-incremented by DB
        session_id="abc123",
        source_ref="orders.csv",
        row_data={"order_id": 1, "amount": -50},
        issue_type="negative_amount",
        issue_column="amount",
        severity="critical",
        detected_by="deterministic",
        suggestion="Review order amount",
        status="pending",
        resolved_at=None,
        resolved_by=None,
        created_at=QuarantineRecord._now(),
    )
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional

from rhosocial.activerecord.base.fields import UseSqlType
from rhosocial.activerecord.backend.expression.types import (
    DateTimeType,
    IntegerType,
    JsonType,
    TextType,
    VarCharType,
)
from rhosocial.activerecord.model import ActiveRecord


def _now_iso() -> str:
    """Return current UTC time in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _uuid() -> str:
    """Return a 12-character hex UUID string."""
    return uuid.uuid4().hex[:12]


class QuarantineRecord(ActiveRecord):
    """Row-level quarantine record for data quality issues.

    Stores data rows that failed quality checks, along with metadata about
    the issue type, severity, and resolution status. Used by the quarantine
    mechanism to isolate problematic data before it corrupts downstream
    systems.

    Table: ``quarantine_records``
    """

    __table_name__ = "quarantine_records"

    id: Annotated[int, UseSqlType(IntegerType())]
    """Primary key, auto-incremented by the database."""

    session_id: Annotated[str, UseSqlType(VarCharType(length=64))]
    """Session that detected this issue (links to Session.session_id)."""

    source_ref: Annotated[str, UseSqlType(VarCharType(length=512))]
    """Source identifier (e.g. file path, URL, or table name)."""

    row_data: Annotated[dict, UseSqlType(JsonType())]
    """The problematic data row as a JSON dict (e.g. {"order_id": 1, "amount": -50})."""

    issue_type: Annotated[str, UseSqlType(VarCharType(length=64))]
    """Category of the issue (e.g. "negative_amount", "null_value", "type_error")."""

    issue_column: Annotated[Optional[str], UseSqlType(VarCharType(length=128))]
    """Column name where the issue was found, or None for row-level issues."""

    severity: Annotated[str, UseSqlType(VarCharType(length=16))]
    """Issue severity: ``"critical"`` (blocks processing) or ``"warning"`` (flagged)."""

    detected_by: Annotated[str, UseSqlType(VarCharType(length=32))]
    """Detection method: ``"deterministic"``, ``"llm"``, or ``"schema_drift"``."""

    suggestion: Annotated[Optional[str], UseSqlType(TextType())]
    """Suggested fix or action for this issue."""

    status: Annotated[str, UseSqlType(VarCharType(length=16))]
    """Resolution status: ``"pending"``, ``"approved"``, ``"rejected"``, or ``"archived"``."""

    resolved_at: Annotated[Optional[str], UseSqlType(DateTimeType())]
    """Timestamp when the issue was resolved (ISO 8601)."""

    resolved_by: Annotated[Optional[str], UseSqlType(VarCharType(length=64))]
    """User or system that resolved the issue."""

    created_at: Annotated[str, UseSqlType(DateTimeType())]
    """Timestamp when the record was created (ISO 8601)."""


class OrderEvent(ActiveRecord):
    """Event sourcing record for the complete operation causal chain.

    Every user message, assistant response, tool call, and error is recorded
    as an event with sequence numbers and causal links. Enables full replay
    and audit of agent behavior.

    Table: ``order_events``
    """

    __table_name__ = "order_events"

    id: Annotated[int, UseSqlType(IntegerType())]
    """Primary key, auto-incremented by the database."""

    session_id: Annotated[str, UseSqlType(VarCharType(length=64))]
    """Session this event belongs to."""

    seq_num: Annotated[int, UseSqlType(IntegerType())]
    """Sequence number within the session (1, 2, 3, ...)."""

    event_type: Annotated[str, UseSqlType(VarCharType(length=32))]
    """Event category: ``"user_msg"``, ``"assistant_msg"``, ``"tool_call"``, ``"tool_result"``, or ``"error"``."""

    role: Annotated[str, UseSqlType(VarCharType(length=16))]
    """Actor role: ``"user"``, ``"assistant"``, ``"tool"``, or ``"system"``."""

    content: Annotated[Optional[str], UseSqlType(TextType())]
    """Text content for message events (user/assistant messages, error text)."""

    tool_name: Annotated[Optional[str], UseSqlType(VarCharType(length=64))]
    """Tool name for tool_call events (e.g. ``"parse_data"``)."""

    tool_args: Annotated[Optional[dict], UseSqlType(JsonType())]
    """Tool arguments for tool_call events."""

    tool_result: Annotated[Optional[dict], UseSqlType(JsonType())]
    """Tool result for tool_call events."""

    latency_ms: Annotated[Optional[int], UseSqlType(IntegerType())]
    """Execution time in milliseconds (for tool_call events)."""

    token_input: Annotated[Optional[int], UseSqlType(IntegerType())]
    """Input token count (for LLM call events)."""

    token_output: Annotated[Optional[int], UseSqlType(IntegerType())]
    """Output token count (for LLM call events)."""

    causation_id: Annotated[Optional[str], UseSqlType(VarCharType(length=64))]
    """ID of the event that directly caused this event (causal chain)."""

    correlation_id: Annotated[Optional[str], UseSqlType(VarCharType(length=64))]
    """ID linking related events across a single operation."""

    metadata: Annotated[Optional[dict], UseSqlType(JsonType())]
    """Additional metadata (e.g. model name, retry count)."""

    created_at: Annotated[str, UseSqlType(DateTimeType())]
    """Timestamp when the event was created (ISO 8601)."""


class SchemaBaseline(ActiveRecord):
    """Schema baseline snapshot for drift detection.

    Stores a known-good schema for a data source. When the schema is later
    inferred from actual data, it can be compared against this baseline to
    detect drift (added/removed/changed fields).

    Table: ``schema_baselines``
    """

    __table_name__ = "schema_baselines"

    id: Annotated[int, UseSqlType(IntegerType())]
    """Primary key, auto-incremented by the database."""

    source_ref: Annotated[str, UseSqlType(VarCharType(length=512))]
    """Source identifier (e.g. file path or URL)."""

    schema_json: Annotated[dict, UseSqlType(JsonType())]
    """Schema definition as JSON (e.g. {"fields": [{"name": "id", "type": "INTEGER"}]})."""

    content_hash: Annotated[str, UseSqlType(VarCharType(length=128))]
    """SHA-256 hash of the schema content (first 16 chars) for quick comparison."""

    row_count: Annotated[Optional[int], UseSqlType(IntegerType())]
    """Number of rows in the source data when this baseline was captured."""

    is_current: Annotated[bool, UseSqlType(IntegerType())]
    """Whether this is the current baseline (1) or a historical version (0)."""

    created_at: Annotated[str, UseSqlType(DateTimeType())]
    """Timestamp when the baseline was created (ISO 8601)."""
