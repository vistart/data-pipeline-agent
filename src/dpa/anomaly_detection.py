"""Statistical anomaly detection for data quality (Layer 2).

Provides automated checks for common data anomalies that can occur
during ETL transformations. These checks run without LLM involvement
and serve as a deterministic safety net.

Checks performed:
    - Row count anomaly (sudden drop/spike)
    - Null rate increase
    - NaN/Inf values in numeric columns
    - Distribution shift (mean deviation)
    - Range anomaly (min/max out of bounds)
    - JOIN inflation (row explosion after join)

Usage::

    from dpa.anomaly_detection import StatisticalDetector

    # Single check
    issue = StatisticalDetector.detect_row_count_anomaly(
        input_rows=1000, output_rows=500, operation="transform"
    )

    # Run all checks
    issues = StatisticalDetector.run_all_checks(
        input_data={"row_count": 1000, "null_rate": 0.02},
        output_data={"row_count": 500, "null_rate": 0.15},
        operation="transform",
    )
"""

from __future__ import annotations

import math
from typing import Any


class StatisticalDetector:
    """Statistical anomaly detector for data quality checks (Layer 2).

    All methods are static and return either a violation dict or None.
    Each violation dict has ``type``, ``severity``, and ``message`` keys.
    """

    @staticmethod
    def detect_row_count_anomaly(
        input_rows: int, output_rows: int, operation: str = "general"
    ) -> dict | None:
        """Detect abnormal row count changes after a transformation.

        For non-filter operations, flags if output rows are less than 50%
        or more than 200% of input rows. For filter operations, only flags
        if rows increased (unexpected).

        Args:
            input_rows: Row count before transformation.
            output_rows: Row count after transformation.
            operation: Type of operation (``"filter"``, ``"general"``).

        Returns:
            Violation dict if anomaly detected, None otherwise.
        """
        if operation == "filter":
            # Filter operations are expected to reduce rows
            if output_rows > input_rows:
                return {
                    "type": "row_count_anomaly",
                    "severity": "warning",
                    "message": f"Filter operation increased rows: {input_rows} -> {output_rows}",
                }
            return None

        ratio = output_rows / max(input_rows, 1)
        if ratio < 0.5 or ratio > 2.0:
            return {
                "type": "row_count_anomaly",
                "severity": "critical",
                "message": f"Row count anomaly: {input_rows} -> {output_rows} (ratio {ratio:.2f})",
            }
        return None

    @staticmethod
    def detect_null_rate_increase(
        input_null_rate: float, output_null_rate: float, threshold: float = 0.05
    ) -> dict | None:
        """Detect unexpected increase in null value rate.

        Args:
            input_null_rate: Null rate before transformation (0.0 to 1.0).
            output_null_rate: Null rate after transformation (0.0 to 1.0).
            threshold: Maximum allowed increase (default 5%).

        Returns:
            Violation dict if increase exceeds threshold, None otherwise.
        """
        increase = output_null_rate - input_null_rate
        if increase > threshold:
            return {
                "type": "null_rate_increase",
                "severity": "warning",
                "message": f"Null rate increased by {increase:.1%} (>{threshold:.1%})",
            }
        return None

    @staticmethod
    def detect_nan_inf(values: list[float]) -> dict | None:
        """Detect NaN or Inf values in a numeric column.

        Args:
            values: List of numeric values to check.

        Returns:
            Violation dict if NaN/Inf found, None otherwise.
        """
        nan_count = sum(1 for v in values if math.isnan(v))
        inf_count = sum(1 for v in values if math.isinf(v))
        if nan_count > 0 or inf_count > 0:
            return {
                "type": "nan_inf_detected",
                "severity": "critical",
                "message": f"Found {nan_count} NaN and {inf_count} Inf values",
            }
        return None

    @staticmethod
    def detect_distribution_shift(
        input_values: list[float], output_values: list[float], threshold: float = 0.3
    ) -> dict | None:
        """Detect distribution shift by comparing mean values.

        Args:
            input_values: Numeric values before transformation.
            output_values: Numeric values after transformation.
            threshold: Maximum allowed deviation ratio (default 30%).

        Returns:
            Violation dict if deviation exceeds threshold, None otherwise.
        """
        if not input_values or not output_values:
            return None

        input_mean = sum(input_values) / len(input_values)
        output_mean = sum(output_values) / len(output_values)

        if input_mean == 0:
            return None

        deviation = abs(output_mean - input_mean) / abs(input_mean)
        if deviation > threshold:
            return {
                "type": "distribution_shift",
                "severity": "warning",
                "message": f"Mean shifted by {deviation:.1%} (>{threshold:.1%}): {input_mean:.2f} -> {output_mean:.2f}",
            }
        return None

    @staticmethod
    def detect_range_anomaly(
        values: list[float], min_bound: float | None = None, max_bound: float | None = None
    ) -> dict | None:
        """Detect values outside expected range bounds.

        Args:
            values: List of numeric values to check.
            min_bound: Expected minimum value (optional).
            max_bound: Expected maximum value (optional).

        Returns:
            Violation dict if out-of-bounds values found, None otherwise.
        """
        if not values:
            return None

        actual_min = min(values)
        actual_max = max(values)
        issues = []

        if min_bound is not None and actual_min < min_bound:
            issues.append(f"min {actual_min} < {min_bound}")
        if max_bound is not None and actual_max > max_bound:
            issues.append(f"max {actual_max} > {max_bound}")

        if issues:
            return {
                "type": "range_anomaly",
                "severity": "warning",
                "message": f"Range anomaly: {'; '.join(issues)}",
            }
        return None

    @staticmethod
    def detect_join_inflation(
        input_rows: int, output_rows: int, threshold: float = 5.0
    ) -> dict | None:
        """Detect row explosion after a JOIN operation.

        Args:
            input_rows: Row count before the JOIN.
            output_rows: Row count after the JOIN.
            threshold: Maximum allowed inflation ratio (default 5x).

        Returns:
            Violation dict if inflation exceeds threshold, None otherwise.
        """
        if input_rows == 0:
            return None
        ratio = output_rows / input_rows
        if ratio > threshold:
            return {
                "type": "join_inflation",
                "severity": "critical",
                "message": f"JOIN inflated rows by {ratio:.1f}x (>{threshold}x): {input_rows} -> {output_rows}",
            }
        return None

    @staticmethod
    def run_all_checks(
        input_data: dict, output_data: dict, operation: str = "general"
    ) -> list[dict]:
        """Run all statistical checks and return any detected issues.

        Args:
            input_data: Input data metadata dict with keys like
                ``"row_count"``, ``"null_rate"``, ``"numeric_values"``.
            output_data: Output data metadata dict (same structure).
            operation: Type of operation performed.

        Returns:
            List of violation dicts (empty if no issues detected).
        """
        issues = []

        # Row count check
        input_rows = input_data.get("row_count", 0)
        output_rows = output_data.get("row_count", 0)
        issue = StatisticalDetector.detect_row_count_anomaly(input_rows, output_rows, operation)
        if issue:
            issues.append(issue)

        # Null rate check
        input_null_rate = input_data.get("null_rate", 0)
        output_null_rate = output_data.get("null_rate", 0)
        issue = StatisticalDetector.detect_null_rate_increase(input_null_rate, output_null_rate)
        if issue:
            issues.append(issue)

        # NaN/Inf check
        output_values = output_data.get("numeric_values", [])
        if output_values:
            issue = StatisticalDetector.detect_nan_inf(output_values)
            if issue:
                issues.append(issue)

        # Distribution shift check
        input_values = input_data.get("numeric_values", [])
        if input_values and output_values:
            issue = StatisticalDetector.detect_distribution_shift(input_values, output_values)
            if issue:
                issues.append(issue)

        return issues
