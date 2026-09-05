"""Tool implementations for the data pipeline agent.

Each class extends `Tool` and implements the `run()` method. Tools are
auto-registered via ``__init_subclass__`` (inherited from `Tool`).

Supported tools:
    - ParseData: Parse CSV/JSON files into structured data
    - SchemaInfer: Infer schema and detect drift
    - ValidateQuality: Run data quality checks
    - TransformData: Apply rename/cast/filter transformations
    - QueryDB: Execute PostgreSQL ORM queries (7 modes)
    - SendAlert: Send alerts via console/file/log channels
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from dpa.tools.base import Tool


class ParseData(Tool):
    """Parse raw data from various formats (CSV, JSON) into structured data.

    Supports auto-detection of format from file extension, or explicit format
    override via the ``format`` parameter.

    Args:
        source (str): File path to the data source.
        format (str, optional): Force format (``"csv"`` or ``"json"``).
            If ``"auto"`` or omitted, detects from file extension.

    Returns:
        dict with keys:
            - ``status`` (str): ``"ok"`` or ``"error"``
            - ``format`` (str): detected format
            - ``source`` (str): file path
            - ``row_count`` (int): number of rows
            - ``fields`` (list[str]): column names
            - ``sample`` (list[dict]): first 3 rows
    """

    name = "parse_data"
    description = "Parse raw data from various formats (CSV, JSON) into a structured representation."

    def run(self, **kwargs: Any) -> Any:
        """Execute the parse operation.

        Raises no exceptions — all errors are returned in the result dict.
        """
        source = kwargs.get("source", "")
        fmt = kwargs.get("format", "auto")

        path = Path(source)
        if not path.exists():
            return {"status": "error", "message": f"File not found: {source}"}

        if fmt == "auto":
            fmt = path.suffix.lstrip(".")

        try:
            if fmt == "csv":
                return self._parse_csv(path)
            elif fmt == "json":
                return self._parse_json(path)
            else:
                return {"status": "error", "message": f"Unsupported format: {fmt}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _parse_csv(self, path: Path) -> dict:
        """Parse a CSV file and return structured result."""
        with open(path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fields = list(rows[0].keys()) if rows else []
            return {
                "status": "ok",
                "format": "csv",
                "source": str(path),
                "row_count": len(rows),
                "fields": fields,
                "sample": rows[:3],
            }

    def _parse_json(self, path: Path) -> dict:
        """Parse a JSON file and return structured result."""
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return {
                "status": "ok",
                "format": "json",
                "source": str(path),
                "row_count": len(data),
                "fields": list(data[0].keys()) if data else [],
                "sample": data[:3],
            }
        return {"status": "ok", "format": "json", "source": str(path), "data": data}


class SchemaInfer(Tool):
    """Infer schema of a dataset and optionally detect drift against a known schema.

    Infers field types by sampling values and testing against INTEGER, NUMERIC,
    DATE, and TEXT patterns. When ``known_schema`` is provided, computes added,
    removed, and type-changed fields.

    Args:
        source (str): File path to the data source (CSV).
        known_schema (dict, optional): Previous schema to compare against.
            Must have a ``"fields"`` key with a list of field dicts.

    Returns:
        dict with keys:
            - ``status`` (str): ``"ok"`` or ``"error"``
            - ``schema`` (dict): inferred schema (when no known_schema)
            - ``drift`` (dict): drift details (when known_schema provided)
            - ``has_drift`` (bool): whether drift was detected
    """

    name = "schema_infer"
    description = "Infer or compare schema of a dataset. Detect drift by comparing against a known schema."

    def run(self, **kwargs: Any) -> Any:
        """Execute schema inference or drift detection."""
        source = kwargs.get("source", "")
        known_schema = kwargs.get("known_schema")

        path = Path(source)
        if not path.exists():
            return {"status": "error", "message": f"File not found: {source}"}

        try:
            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            if not rows:
                return {"status": "error", "message": "Empty dataset"}

            current_schema = self._infer_schema(rows)

            if known_schema:
                drift = self._detect_drift(known_schema, current_schema)
                return {
                    "status": "ok",
                    "source": source,
                    "current_schema": current_schema,
                    "known_schema": known_schema,
                    "drift": drift,
                    "has_drift": bool(drift["added"] or drift["removed"] or drift["type_changed"]),
                }

            return {
                "status": "ok",
                "source": source,
                "schema": current_schema,
                "row_count": len(rows),
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _infer_schema(self, rows: list[dict]) -> dict:
        """Infer schema from CSV rows by sampling values."""
        fields = {}
        for col in rows[0].keys():
            values = [r[col] for r in rows if r.get(col)]
            field_info = {
                "name": col,
                "type": self._detect_type(values),
                "nullable": any(not r.get(col) for r in rows),
                "unique_count": len(set(values)),
                "sample_values": list(set(values))[:5],
            }
            fields[col] = field_info
        return {"fields": list(fields.values())}

    def _detect_type(self, values: list[str]) -> str:
        """Detect the most likely SQL type for a list of string values.

        Tries INTEGER -> NUMERIC -> DATE -> TEXT in order of specificity.
        """
        if not values:
            return "TEXT"
        try:
            [int(v) for v in values]
            return "INTEGER"
        except (ValueError, TypeError):
            pass
        try:
            [float(v) for v in values]
            return "NUMERIC"
        except (ValueError, TypeError):
            pass
        try:
            [datetime.strptime(v, "%Y-%m-%d") for v in values]
            return "DATE"
        except (ValueError, TypeError):
            pass
        return "TEXT"

    def _detect_drift(self, known: dict, current: dict) -> dict:
        """Compute schema differences between known and current schemas.

        Returns:
            dict with ``added``, ``removed``, and ``type_changed`` lists.
        """
        known_fields = {f["name"]: f for f in known.get("fields", [])}
        current_fields = {f["name"]: f for f in current.get("fields", [])}

        added = []
        removed = []
        type_changed = []

        for name in current_fields:
            if name not in known_fields:
                added.append({"name": name, "type": current_fields[name]["type"]})

        for name in known_fields:
            if name not in current_fields:
                removed.append({"name": name, "type": known_fields[name]["type"]})

        for name in known_fields:
            if name in current_fields:
                if known_fields[name]["type"] != current_fields[name]["type"]:
                    type_changed.append({
                        "name": name,
                        "old_type": known_fields[name]["type"],
                        "new_type": current_fields[name]["type"],
                    })

        return {"added": added, "removed": removed, "type_changed": type_changed}


class ValidateQuality(Tool):
    """Run data quality checks on a CSV dataset.

    Checks for null values, type mismatches, and range violations. Each
    violation is categorized by severity (``critical`` or ``warning``).

    Args:
        source (str): File path to the CSV data source.
        rules (list[dict], optional): Custom validation rules (reserved for
            future use; current checks are hardcoded).

    Returns:
        dict with keys:
            - ``status`` (str): ``"ok"`` or ``"error"``
            - ``row_count`` (int): total rows scanned
            - ``violation_count`` (int): number of issues found
            - ``violations`` (list[dict]): detailed issue list
            - ``passed`` (bool): True if no violations
    """

    name = "validate_quality"
    description = "Run data quality checks (nulls, types, ranges, uniqueness) on a dataset."

    def run(self, **kwargs: Any) -> Any:
        """Execute quality validation."""
        source = kwargs.get("source", "")
        rules = kwargs.get("rules", [])

        path = Path(source)
        if not path.exists():
            return {"status": "error", "message": f"File not found: {source}"}

        try:
            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)

            violations = []
            for i, row in enumerate(rows):
                for col in row:
                    val = row[col]
                    if not val or val.strip() == "":
                        violations.append({
                            "row": i + 1,
                            "column": col,
                            "issue": "null_value",
                            "severity": "warning",
                        })
                    elif col == "quantity":
                        try:
                            q = int(val)
                            if q < 0:
                                violations.append({
                                    "row": i + 1,
                                    "column": col,
                                    "issue": f"negative_value: {val}",
                                    "severity": "critical",
                                })
                        except ValueError:
                            violations.append({
                                "row": i + 1,
                                "column": col,
                                "issue": f"type_error: {val}",
                                "severity": "critical",
                            })
                    elif col == "price":
                        try:
                            float(val)
                        except ValueError:
                            violations.append({
                                "row": i + 1,
                                "column": col,
                                "issue": f"type_error: {val}",
                                "severity": "critical",
                            })

            return {
                "status": "ok",
                "source": source,
                "row_count": len(rows),
                "violation_count": len(violations),
                "violations": violations,
                "passed": len(violations) == 0,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


class TransformData(Tool):
    """Apply transformations (rename, cast, filter) to a CSV dataset.

    Supports chained transformations applied in order. Results can be
    written to a new file or overwrite the source.

    Supported ops:
        - ``rename``: Rename a column (``from`` -> ``to``)
        - ``cast``: Cast column values to a target type (``NUMERIC``/``INTEGER``)
        - ``filter``: Filter rows by condition (``eq``/``ne``/``gt``/``lt``)

    Args:
        source (str): File path to the CSV data source.
        transforms (list[dict]): List of transformation operations.
        output (str, optional): Output file path. If empty, modifies in-place.

    Returns:
        dict with keys:
            - ``status`` (str): ``"ok"`` or ``"error"``
            - ``rows_affected`` (int): number of rows modified
            - ``total_rows`` (int): total rows after transformation
            - ``fields`` (list[str]): final column names
    """

    name = "transform_data"
    description = "Apply transformations (rename, cast, filter, add_column) to a dataset."

    def run(self, **kwargs: Any) -> Any:
        """Execute transformations on the dataset."""
        source = kwargs.get("source", "")
        transforms = kwargs.get("transforms", [])
        output = kwargs.get("output", "")

        path = Path(source)
        if not path.exists():
            return {"status": "error", "message": f"File not found: {source}"}

        try:
            with open(path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                fields = list(reader.fieldnames or [])

            rows_affected = 0
            for t in transforms:
                op = t.get("op", "")
                if op == "rename":
                    old_name = t.get("from", "")
                    new_name = t.get("to", "")
                    if old_name in fields:
                        for row in rows:
                            row[new_name] = row.pop(old_name, "")
                        fields = [new_name if f == old_name else f for f in fields]
                        rows_affected = len(rows)
                elif op == "cast":
                    col = t.get("column", "")
                    target_type = t.get("type", "NUMERIC")
                    for row in rows:
                        if col in row:
                            try:
                                if target_type == "NUMERIC":
                                    row[col] = float(row[col]) if row[col] else 0
                                elif target_type == "INTEGER":
                                    row[col] = int(float(row[col])) if row[col] else 0
                                rows_affected += 1
                            except (ValueError, TypeError):
                                pass
                elif op == "filter":
                    col = t.get("column", "")
                    op_type = t.get("operator", "eq")
                    val = t.get("value", "")
                    new_rows = []
                    for row in rows:
                        if col in row:
                            keep = False
                            if op_type == "eq" and row[col] == val:
                                keep = True
                            elif op_type == "ne" and row[col] != val:
                                keep = True
                            elif op_type == "gt" and float(row[col]) > float(val):
                                keep = True
                            elif op_type == "lt" and float(row[col]) < float(val):
                                keep = True
                            if keep:
                                new_rows.append(row)
                    rows_affected = len(rows) - len(new_rows)
                    rows = new_rows

            if output:
                out_path = Path(output)
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with open(out_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.DictWriter(f, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)

            return {
                "status": "ok",
                "source": source,
                "output": output or source,
                "rows_affected": rows_affected,
                "total_rows": len(rows),
                "fields": fields,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}


class QueryDB(Tool):
    """Query PostgreSQL database using ORM-style operations.

    Supports 7 query modes:
        - ``describe``: Show table column definitions
        - ``count``: Count rows in a table
        - ``select``: Fetch rows with optional limit
        - ``raw``: Execute raw SQL query
        - ``aggregate``: (reserved)
        - ``join``: (reserved)
        - ``exists``: (reserved)

    Args:
        mode (str): Query mode (default: ``"select"``).
        table (str): Target table name.
        limit (int, optional): Row limit for select mode (default: 10).
        query (str, optional): Raw SQL for ``"raw"`` mode.

    Returns:
        dict with keys:
            - ``status`` (str): ``"ok"`` or ``"error"``
            - ``columns`` (list[str]): column names (select/raw modes)
            - ``rows`` (list[dict]): result rows (select/raw modes)
            - ``count`` (int): row count (count mode)
            - ``columns`` (list[dict]): column definitions (describe mode)
    """

    name = "query_db"
    description = "Query the database using ORM-native operations (select, aggregate, join, exists, count, describe, raw)."

    def run(self, **kwargs: Any) -> Any:
        """Execute a database query.

        Uses psycopg3 directly for query execution. Connection is read from
        ``DATABASE_URL`` environment variable.
        """
        mode = kwargs.get("mode", "select")
        table = kwargs.get("table", "")
        db_url = os.getenv("DATABASE_URL", "")

        if not db_url:
            return {"status": "error", "message": "DATABASE_URL not configured"}

        try:
            import psycopg
            conn = psycopg.connect(db_url)
            cur = conn.cursor()

            if mode == "describe":
                cur.execute(f"""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY ordinal_position
                """, (table,))
                columns = cur.fetchall()
                return {
                    "status": "ok",
                    "table": table,
                    "columns": [{"name": c[0], "type": c[1], "nullable": c[2]} for c in columns],
                }

            elif mode == "count":
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                return {"status": "ok", "table": table, "count": count}

            elif mode == "select":
                limit = kwargs.get("limit", 10)
                cur.execute(f"SELECT * FROM {table} LIMIT %s", (limit,))
                columns = [desc[0] for desc in cur.description]
                rows = cur.fetchall()
                return {
                    "status": "ok",
                    "table": table,
                    "columns": columns,
                    "rows": [dict(zip(columns, row)) for row in rows],
                    "count": len(rows),
                }

            elif mode == "raw":
                query = kwargs.get("query", "")
                cur.execute(query)
                if cur.description:
                    columns = [desc[0] for desc in cur.description]
                    rows = cur.fetchall()
                    return {"status": "ok", "columns": columns, "rows": [dict(zip(columns, row)) for row in rows]}
                return {"status": "ok", "message": "Query executed (no result set)"}

            else:
                return {"status": "error", "message": f"Unknown mode: {mode}"}

        except Exception as e:
            return {"status": "error", "message": str(e)}
        finally:
            if "conn" in locals():
                conn.close()


class SendAlert(Tool):
    """Send alerts via configured channels.

    Channels:
        - ``console``: Print to stdout with level prefix and timestamp
        - ``file``: Append to ``logs/alerts.jsonl`` in JSONL format
        - ``log``: Return structured log entry (for programmatic use)

    Args:
        level (str): Alert severity (``info``/``warning``/``error``/``critical``).
        message (str): Alert message text.
        channel (str): Delivery channel (``console``/``file``/``log``).

    Returns:
        dict with keys:
            - ``status`` (str): ``"ok"`` or ``"error"``
            - ``channel`` (str): delivery channel used
    """

    name = "send_alert"
    description = "Send alerts via configured channels (console, log, file)."

    def run(self, **kwargs: Any) -> Any:
        """Send an alert through the specified channel."""
        level = kwargs.get("level", "info")
        message = kwargs.get("message", "")
        channel = kwargs.get("channel", "console")

        timestamp = datetime.now().isoformat()
        alert_entry = {"level": level, "message": message, "timestamp": timestamp}

        if channel == "console":
            prefix = {"info": "INFO", "warning": "WARN", "error": "ERROR", "critical": "CRIT"}.get(level, "INFO")
            print(f"[{prefix}] [{timestamp}] {message}")
            return {"status": "ok", "channel": "console", "message": message}

        elif channel == "file":
            log_path = Path("logs/alerts.jsonl")
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(alert_entry, ensure_ascii=False) + "\n")
            return {"status": "ok", "channel": "file", "path": str(log_path)}

        elif channel == "log":
            return {"status": "ok", "channel": "log", "entry": alert_entry}

        else:
            return {"status": "error", "message": f"Unknown channel: {channel}"}
