from __future__ import annotations

import json
from typing import Any

import pandas as pd
import streamlit as st

from petrolab.db import connect


_CONTEXT_KEY = "_petrolab_work_context"
_RECENT_LIMIT = 8


def _ensure_recent_schema() -> None:
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS ui_recent_contexts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                context_kind TEXT NOT NULL,
                context_label TEXT NOT NULL,
                selector_json TEXT NOT NULL DEFAULT '{}',
                opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, context_kind, context_label),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_ui_recent_contexts_project ON ui_recent_contexts(project_id, opened_at DESC)"
        )
        con.commit()


def _record_recent(project_id: int, kind: str, label: str, selector: dict[str, Any]) -> None:
    _ensure_recent_schema()
    payload = json.dumps(selector, ensure_ascii=False, sort_keys=True, default=str)
    with connect() as con:
        con.execute(
            """INSERT INTO ui_recent_contexts(project_id,context_kind,context_label,selector_json,opened_at)
               VALUES(?,?,?,?,CURRENT_TIMESTAMP)
               ON CONFLICT(project_id,context_kind,context_label)
               DO UPDATE SET selector_json=excluded.selector_json, opened_at=CURRENT_TIMESTAMP""",
            (int(project_id), str(kind), str(label), payload),
        )
        con.execute(
            """DELETE FROM ui_recent_contexts
               WHERE project_id=? AND id NOT IN (
                   SELECT id FROM ui_recent_contexts WHERE project_id=? ORDER BY opened_at DESC, id DESC LIMIT ?
               )""",
            (int(project_id), int(project_id), int(_RECENT_LIMIT)),
        )
        con.commit()


def set_work_context(
    *,
    project_id: int,
    kind: str,
    label: str,
    dataset_ids: list[int] | tuple[int, ...] = (),
    analysis_ids: list[str] | tuple[str, ...] = (),
    sample: str | None = None,
    sample_id: int | None = None,
    thin_section_id: int | None = None,
) -> dict[str, Any]:
    context = {
        "project_id": int(project_id),
        "kind": str(kind),
        "label": str(label),
        "dataset_ids": [int(value) for value in dataset_ids],
        "analysis_ids": [str(value) for value in analysis_ids],
        "sample": str(sample) if sample else None,
        "sample_id": int(sample_id) if sample_id is not None else None,
        "thin_section_id": int(thin_section_id) if thin_section_id is not None else None,
    }
    st.session_state[_CONTEXT_KEY] = context
    selector: dict[str, Any] = {}
    if sample:
        selector["sample"] = str(sample)
    if sample_id is not None:
        selector["sample_id"] = int(sample_id)
    if dataset_ids:
        selector["dataset_ids"] = [int(value) for value in dataset_ids]
    if thin_section_id is not None:
        selector["thin_section_id"] = int(thin_section_id)
    _record_recent(int(project_id), str(kind), str(label), selector)
    return context


def get_work_context(project_id: int | None = None) -> dict[str, Any] | None:
    value = st.session_state.get(_CONTEXT_KEY)
    if not isinstance(value, dict):
        return None
    if project_id is not None and int(value.get("project_id", -1)) != int(project_id):
        return None
    return dict(value)


def clear_work_context() -> None:
    st.session_state.pop(_CONTEXT_KEY, None)


def list_recent_work_contexts(project_id: int, limit: int = 4) -> list[dict[str, Any]]:
    _ensure_recent_schema()
    with connect() as con:
        rows = con.execute(
            """SELECT context_kind, context_label, selector_json, opened_at
               FROM ui_recent_contexts WHERE project_id=?
               ORDER BY opened_at DESC, id DESC LIMIT ?""",
            (int(project_id), max(1, int(limit))),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        try:
            selector = json.loads(str(row["selector_json"] or "{}"))
        except json.JSONDecodeError:
            selector = {}
        result.append({
            "kind": str(row["context_kind"]),
            "label": str(row["context_label"]),
            "selector": selector if isinstance(selector, dict) else {},
            "opened_at": str(row["opened_at"]),
        })
    return result


def _table_exists(con, name: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (str(name),)
    ).fetchone())


def _thin_section_analysis_ids(project_id: int, thin_section_id: int) -> set[str]:
    """Resolve explicit links for a thin section; never broaden to the whole Sample."""
    result: set[str] = set()
    with connect() as con:
        if _table_exists(con, "physical_point_analysis_links") and _table_exists(con, "physical_entities"):
            rows = con.execute(
                """SELECT l.analysis_id
                   FROM physical_point_analysis_links l
                   JOIN physical_entities e ON e.id=l.entity_id
                   WHERE e.project_id=? AND e.parent_id=?""",
                (int(project_id), int(thin_section_id)),
            ).fetchall()
            result.update(str(row["analysis_id"]) for row in rows)
        if all(_table_exists(con, name) for name in (
            "slide_images", "slide_markers", "slide_marker_analysis_links"
        )):
            rows = con.execute(
                """SELECT ml.analysis_id
                   FROM slide_marker_analysis_links ml
                   JOIN slide_markers m ON m.id=ml.marker_id
                   JOIN slide_images i ON i.id=m.slide_image_id
                   WHERE m.project_id=? AND i.thin_section_id=?""",
                (int(project_id), int(thin_section_id)),
            ).fetchall()
            result.update(str(row["analysis_id"]) for row in rows)
    return result


def _sample_name_for_id(project_id: int, sample_id: int) -> str:
    with connect() as con:
        if not _table_exists(con, "samples"):
            return ""
        row = con.execute(
            "SELECT name FROM samples WHERE id=? AND project_id=?",
            (int(sample_id), int(project_id)),
        ).fetchone()
    return str(row["name"]) if row else ""


def filter_dataframe_to_context(dataframe: pd.DataFrame, context: dict[str, Any] | None) -> pd.DataFrame:
    """Apply compatible context selectors together without silently broadening a physical scope.

    For Sample/dataset contexts the selectors are intersections. For a thin section,
    an explicit physical/marker link is the authoritative membership relation; raw
    ``Sample`` text in the imported analytical row is provenance and may legitimately
    differ by alias or spelling, so it must not throw out a physically linked analysis.
    """
    if dataframe.empty or not context:
        return dataframe
    result = dataframe.copy()
    project_id = int(context.get("project_id", -1))

    analysis_ids = {str(value) for value in context.get("analysis_ids", []) if str(value)}
    if analysis_ids and "_analysis_id" in result.columns:
        result = result[result["_analysis_id"].astype(str).isin(analysis_ids)].copy()

    dataset_ids = {int(value) for value in context.get("dataset_ids", [])}
    if dataset_ids and "_dataset_id" in result.columns:
        numeric = pd.to_numeric(result["_dataset_id"], errors="coerce")
        result = result[numeric.isin(dataset_ids)].copy()

    thin_section_id = context.get("thin_section_id")
    physical_scope_applied = False
    if thin_section_id is not None and "_analysis_id" in result.columns:
        linked_ids = _thin_section_analysis_ids(project_id, int(thin_section_id))
        # An empty explicit link set means the thin section has no linked analyses yet.
        # Returning all analyses from its Sample would be a scientifically unsafe broadening.
        result = result[result["_analysis_id"].astype(str).isin(linked_ids)].copy()
        physical_scope_applied = True

    sample = str(context.get("sample") or "").strip()
    if not sample and context.get("sample_id") is not None and project_id >= 0:
        sample = _sample_name_for_id(project_id, int(context["sample_id"]))
    if sample and "Sample" in result.columns and not physical_scope_applied:
        result = result[result["Sample"].astype(str).str.casefold() == sample.casefold()].copy()
    return result
