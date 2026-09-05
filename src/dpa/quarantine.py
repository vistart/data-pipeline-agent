"""Quarantine mechanism for data quality issues.

Isolates data rows that fail quality checks into a quarantine area
(backed by the ``quarantine_records`` table). Supports approval workflow
for reviewing and resolving quarantined items.

Quarantine flow::

    1. Quality check detects issues
    2. QuarantineManager.classify_issues() categorizes by severity
    3. QuarantineManager.should_quarantine() decides if isolation needed
    4. QuarantineManager.isolate() creates a quarantine record
    5. User reviews via approve()/reject()

Usage::

    from dpa.quarantine import QuarantineManager

    # Classify violations
    classified = QuarantineManager.classify_issues(violations)

    # Check if quarantine is needed (critical ratio > 10%)
    if QuarantineManager.should_quarantine(violations):
        record = QuarantineManager.isolate(
            session_id="abc123",
            source_ref="orders.csv",
            row_data=row,
            issue_type="negative_amount",
            severity="critical",
        )
"""

from __future__ import annotations

from typing import Any

from dpa.models import QuarantineRecord


class QuarantineManager:
    """Manages quarantine records for data quality issues.

    Provides static methods for isolating, reviewing, and resolving
    quarantined data rows. All methods are stateless (no instance needed).
    """

    @staticmethod
    def isolate(
        session_id: str,
        source_ref: str,
        row_data: dict,
        issue_type: str,
        severity: str,
        detected_by: str = "deterministic",
        issue_column: str | None = None,
        suggestion: str | None = None,
    ) -> QuarantineRecord:
        """Create a new quarantine record for a problematic data row.

        Args:
            session_id: Session that detected this issue.
            source_ref: Source identifier (file path, URL, etc.).
            row_data: The problematic data row as a dict.
            issue_type: Category of the issue (e.g. ``"negative_amount"``).
            severity: Issue severity (``"critical"`` or ``"warning"``).
            detected_by: Detection method (``"deterministic"``, ``"llm"``, etc.).
            issue_column: Column name where the issue was found (optional).
            suggestion: Suggested fix (optional).

        Returns:
            A new QuarantineRecord instance (not yet persisted to DB).
        """
        record = QuarantineRecord(
            id=0,  # auto-increment
            session_id=session_id,
            source_ref=source_ref,
            row_data=row_data,
            issue_type=issue_type,
            issue_column=issue_column,
            severity=severity,
            detected_by=detected_by,
            suggestion=suggestion,
            status="pending",
            resolved_at=None,
            resolved_by=None,
            created_at=QuarantineRecord._now(),
        )
        return record

    @staticmethod
    def get_pending(session_id: str | None = None) -> list[dict]:
        """Get pending quarantine records.

        Args:
            session_id: Optional session filter.

        Returns:
            List of pending quarantine record dicts.
        """
        # Simplified implementation (should query DB in production)
        return []

    @staticmethod
    def approve(record_id: int, resolved_by: str = "user") -> dict:
        """Approve a quarantined record for processing.

        Args:
            record_id: ID of the quarantine record.
            resolved_by: User or system approving the record.

        Returns:
            Dict with approval status.
        """
        return {"status": "approved", "record_id": record_id, "resolved_by": resolved_by}

    @staticmethod
    def reject(record_id: int, resolved_by: str = "user") -> dict:
        """Reject a quarantined record (keep it isolated).

        Args:
            record_id: ID of the quarantine record.
            resolved_by: User or system rejecting the record.

        Returns:
            Dict with rejection status.
        """
        return {"status": "rejected", "record_id": record_id, "resolved_by": resolved_by}

    @staticmethod
    def classify_issues(violations: list[dict]) -> dict:
        """Classify quality issues by severity level.

        Args:
            violations: List of violation dicts with ``"severity"`` key.

        Returns:
            Dict with ``"critical"``, ``"warning"``, and ``"info"`` lists.
        """
        classified = {"critical": [], "warning": [], "info": []}
        for v in violations:
            severity = v.get("severity", "info")
            if severity in classified:
                classified[severity].append(v)
        return classified

    @staticmethod
    def should_quarantine(violations: list[dict], threshold: float = 0.1) -> bool:
        """Determine if quarantine is needed based on critical issue ratio.

        Args:
            violations: List of violation dicts.
            threshold: Critical ratio threshold (default 0.1 = 10%).

        Returns:
            True if critical violations exceed the threshold.
        """
        if not violations:
            return False
        critical_count = sum(1 for v in violations if v.get("severity") == "critical")
        return critical_count / len(violations) >= threshold
