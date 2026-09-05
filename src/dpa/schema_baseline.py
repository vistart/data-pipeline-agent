"""Schema baseline management for drift detection.

Stores known-good schema snapshots and compares them against newly
inferred schemas to detect drift (added/removed/changed fields).

Schema baseline flow::

    1. Infer schema from data (SchemaInfer tool)
    2. Save baseline with SchemaBaselineManager.save_baseline()
    3. On subsequent runs, detect drift with detect_drift()
    4. If drift detected, decide whether to update baseline

Baselines are stored as JSON files in the ``schemas/`` directory,
named ``{source_ref}_{content_hash}.json``.

Usage::

    from dpa.schema_baseline import SchemaBaselineManager

    manager = SchemaBaselineManager()

    # Save a baseline
    content_hash = manager.save_baseline(
        source_ref="orders.csv",
        schema={"fields": [{"name": "id", "type": "INTEGER"}]},
        row_count=1000,
    )

    # Detect drift
    result = manager.detect_drift("orders.csv", current_schema)
    if result["has_drift"]:
        print(f"Drift detected: {result['drift']}")
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_DIR = Path("schemas")


class SchemaBaselineManager:
    """Manages schema baseline persistence and drift detection.

    Stores baselines as JSON files with content hashes for quick
    comparison. Supports multiple baselines per source with a
    ``is_current`` flag to track the active baseline.
    """

    def __init__(self) -> None:
        """Initialize the manager, creating the schemas directory if needed."""
        SCHEMA_DIR.mkdir(parents=True, exist_ok=True)

    def _hash_schema(self, schema: dict) -> str:
        """Compute a content hash for a schema dict.

        Args:
            schema: Schema definition dict.

        Returns:
            16-character hex SHA-256 hash of the schema content.
        """
        content = json.dumps(schema, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def save_baseline(self, source_ref: str, schema: dict, row_count: int = 0) -> str:
        """Save a new schema baseline, marking it as current.

        Marks any existing baselines for this source as non-current,
        then saves the new baseline with a content hash.

        Args:
            source_ref: Source identifier (file path, URL, etc.).
            schema: Schema definition dict (e.g. from SchemaInfer tool).
            row_count: Number of rows in the source data.

        Returns:
            Content hash of the saved baseline.
        """
        content_hash = self._hash_schema(schema)
        baseline = {
            "source_ref": source_ref,
            "schema": schema,
            "content_hash": content_hash,
            "row_count": row_count,
            "is_current": True,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Mark old baselines as non-current
        self._clear_current(source_ref)

        # Save new baseline
        path = SCHEMA_DIR / f"{self._safe_filename(source_ref)}_{content_hash}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(baseline, f, ensure_ascii=False, indent=2)

        return content_hash

    def load_baseline(self, source_ref: str) -> dict | None:
        """Load the current schema baseline for a source.

        Args:
            source_ref: Source identifier.

        Returns:
            Schema dict if a baseline exists, None otherwise.
        """
        baselines = self._list_baselines(source_ref)
        for b in baselines:
            if b.get("is_current"):
                return b.get("schema")
        # Fall back to most recent baseline
        if baselines:
            return baselines[-1].get("schema")
        return None

    def detect_drift(self, source_ref: str, current_schema: dict) -> dict:
        """Detect schema drift by comparing against the baseline.

        Args:
            source_ref: Source identifier.
            current_schema: Newly inferred schema.

        Returns:
            Dict with keys:
                - ``status``: ``"ok"`` or ``"no_baseline"``
                - ``has_drift``: bool indicating drift
                - ``baseline_hash``: hash of the baseline schema
                - ``current_hash``: hash of the current schema
                - ``drift``: dict with ``added``, ``removed``, ``type_changed`` lists
        """
        baseline = self.load_baseline(source_ref)
        if baseline is None:
            return {
                "status": "no_baseline",
                "message": "No baseline found for this source",
                "drift": None,
            }

        drift = self._compute_drift(baseline, current_schema)
        return {
            "status": "ok",
            "has_drift": bool(drift["added"] or drift["removed"] or drift["type_changed"]),
            "baseline_hash": self._hash_schema(baseline),
            "current_hash": self._hash_schema(current_schema),
            "drift": drift,
        }

    def _compute_drift(self, baseline: dict, current: dict) -> dict:
        """Compute field-level differences between baseline and current schemas.

        Args:
            baseline: Baseline schema dict.
            current: Current schema dict.

        Returns:
            Dict with ``added``, ``removed``, and ``type_changed`` lists.
        """
        baseline_fields = {f["name"]: f for f in baseline.get("fields", [])}
        current_fields = {f["name"]: f for f in current.get("fields", [])}

        added = []
        removed = []
        type_changed = []

        for name in current_fields:
            if name not in baseline_fields:
                added.append({"name": name, "type": current_fields[name].get("type", "UNKNOWN")})

        for name in baseline_fields:
            if name not in current_fields:
                removed.append({"name": name, "type": baseline_fields[name].get("type", "UNKNOWN")})

        for name in baseline_fields:
            if name in current_fields:
                old_type = baseline_fields[name].get("type", "UNKNOWN")
                new_type = current_fields[name].get("type", "UNKNOWN")
                if old_type != new_type:
                    type_changed.append({
                        "name": name,
                        "old_type": old_type,
                        "new_type": new_type,
                    })

        return {"added": added, "removed": removed, "type_changed": type_changed}

    def _list_baselines(self, source_ref: str) -> list[dict]:
        """List all baselines for a given source.

        Args:
            source_ref: Source identifier.

        Returns:
            List of baseline dicts loaded from JSON files.
        """
        baselines = []
        prefix = self._safe_filename(source_ref)
        for path in SCHEMA_DIR.glob(f"{prefix}_*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    baselines.append(json.load(f))
            except (json.JSONDecodeError, IOError):
                continue
        return baselines

    def _clear_current(self, source_ref: str) -> None:
        """Mark all baselines for a source as non-current.

        Args:
            source_ref: Source identifier.
        """
        for b in self._list_baselines(source_ref):
            if b.get("is_current"):
                b["is_current"] = False
                path = SCHEMA_DIR / f"{self._safe_filename(source_ref)}_{b.get('content_hash', '')}.json"
                if path.exists():
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(b, f, ensure_ascii=False, indent=2)

    def _safe_filename(self, source_ref: str) -> str:
        """Convert a source reference to a filesystem-safe filename.

        Args:
            source_ref: Source identifier (may contain slashes, colons, etc.).

        Returns:
            Safe filename string (max 64 chars).
        """
        return source_ref.replace("/", "_").replace("\\", "_").replace(":", "_")[:64]
