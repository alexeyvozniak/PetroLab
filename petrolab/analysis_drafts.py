from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Iterator

import pandas as pd

from petrolab.dataframe_utils import values_equal
from petrolab.db import DATA_DIR

DRAFT_DB_PATH = DATA_DIR / "analysis_drafts.sqlite3"


@dataclass(frozen=True)
class DraftState:
    changes: tuple[dict[str, Any], ...] = ()
    updated_at: str = ""


@dataclass(frozen=True)
class DraftOverlay:
    dataframe: pd.DataFrame
    applied: tuple[dict[str, Any], ...] = ()
    conflicts: tuple[dict[str, Any], ...] = ()
    resolved: tuple[dict[str, Any], ...] = ()
    unavailable: tuple[dict[str, Any], ...] = ()


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DRAFT_DB_PATH, timeout=5.0)
    con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA busy_timeout=5000")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_edit_drafts (
                project_id INTEGER PRIMARY KEY,
                changes_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        con.commit()
        yield con
    finally:
        con.close()


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _normalise_change(change: dict[str, Any]) -> dict[str, Any]:
    source_row = change.get("source_row")
    return {
        "analysis_id": str(change["analysis_id"]),
        "dataset_id": int(change["dataset_id"]),
        "source_row": None if source_row is None else int(source_row),
        "column_name": str(change["column_name"]),
        "old_value": _json_value(change.get("old_value")),
        "new_value": _json_value(change.get("new_value")),
    }


def _key(change: dict[str, Any]) -> tuple[str, str]:
    return str(change["analysis_id"]), str(change["column_name"])


def _ordered(changes: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {_key(change): _normalise_change(change) for change in changes}
    return [merged[key] for key in sorted(merged)]


def load_analysis_draft(project_id: int) -> DraftState:
    with _connect() as con:
        row = con.execute(
            "SELECT changes_json, updated_at FROM analysis_edit_drafts WHERE project_id=?",
            (int(project_id),),
        ).fetchone()
    if row is None:
        return DraftState()
    try:
        raw = json.loads(row["changes_json"])
    except (TypeError, json.JSONDecodeError):
        raw = []
    changes = tuple(_normalise_change(item) for item in raw if isinstance(item, dict))
    return DraftState(changes=changes, updated_at=str(row["updated_at"] or ""))


def _write(project_id: int, changes: Iterable[dict[str, Any]]) -> DraftState:
    ordered = _ordered(changes)
    if not ordered:
        clear_analysis_draft(project_id)
        return DraftState()
    current = load_analysis_draft(project_id)
    if list(current.changes) == ordered:
        return current
    updated_at = _utcnow()
    payload = json.dumps(ordered, ensure_ascii=False, separators=(",", ":"))
    with _connect() as con:
        con.execute(
            """
            INSERT INTO analysis_edit_drafts(project_id, changes_json, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(project_id) DO UPDATE SET
                changes_json=excluded.changes_json,
                updated_at=excluded.updated_at
            """,
            (int(project_id), payload, updated_at),
        )
        con.commit()
    return DraftState(changes=tuple(ordered), updated_at=updated_at)


def replace_visible_analysis_draft(
    project_id: int,
    visible_analysis_ids: Iterable[str],
    visible_columns: Iterable[str],
    visible_changes: Iterable[dict[str, Any]],
) -> DraftState:
    """Replace only the currently rendered draft cells while preserving hidden work."""
    visible_ids = {str(value) for value in visible_analysis_ids}
    columns = {str(value) for value in visible_columns}
    current = load_analysis_draft(project_id)
    retained = [
        change
        for change in current.changes
        if str(change["analysis_id"]) not in visible_ids
        or str(change["column_name"]) not in columns
    ]
    return _write(project_id, [*retained, *visible_changes])


def remove_analysis_draft_changes(project_id: int, saved_changes: Iterable[dict[str, Any]]) -> DraftState:
    keys = {_key(change) for change in saved_changes}
    current = load_analysis_draft(project_id)
    retained = [change for change in current.changes if _key(change) not in keys]
    return _write(project_id, retained)


def clear_analysis_draft(project_id: int) -> None:
    with _connect() as con:
        con.execute("DELETE FROM analysis_edit_drafts WHERE project_id=?", (int(project_id),))
        con.commit()


def apply_analysis_draft(
    dataframe: pd.DataFrame,
    changes: Iterable[dict[str, Any]],
    *,
    protected_columns: Iterable[str] = (),
) -> DraftOverlay:
    """Overlay compatible draft values without silently overwriting newer database values."""
    working = dataframe.copy()
    if working.empty or "_analysis_id" not in working.columns:
        return DraftOverlay(dataframe=working, unavailable=tuple(changes))

    protected = set(protected_columns)
    row_lookup = {str(value): index for index, value in working["_analysis_id"].items()}
    applied: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []

    for raw in changes:
        change = _normalise_change(raw)
        analysis_id = str(change["analysis_id"])
        column = str(change["column_name"])
        row_index = row_lookup.get(analysis_id)
        if row_index is None or column not in working.columns or column in protected or column.startswith("_"):
            unavailable.append(change)
            continue
        current_value = working.at[row_index, column]
        if values_equal(current_value, change["new_value"]):
            resolved.append(change)
            continue
        if not values_equal(current_value, change["old_value"]):
            conflicts.append(change)
            continue
        working.at[row_index, column] = change["new_value"]
        applied.append(change)

    return DraftOverlay(
        dataframe=working,
        applied=tuple(applied),
        conflicts=tuple(conflicts),
        resolved=tuple(resolved),
        unavailable=tuple(unavailable),
    )
