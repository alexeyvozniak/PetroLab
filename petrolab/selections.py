"""Persistent, non-destructive working selections.

An analysis selection is deliberately distinct from a mineral generation, QC
flag, or a dataset.  It records a research question (for example, "apatites
from article A") and can be reused by charts, thin-section maps and tables
without rewriting the measurements that answer that question.
"""
from __future__ import annotations

import json

from petrolab.db import _utcnow, connect


def ensure_selection_schema() -> None:
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS working_selections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                context_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id, name),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS working_selection_members (
                selection_id INTEGER NOT NULL,
                analysis_id TEXT NOT NULL,
                PRIMARY KEY(selection_id, analysis_id),
                FOREIGN KEY(selection_id) REFERENCES working_selections(id) ON DELETE CASCADE,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_selection_members_analysis ON working_selection_members(analysis_id)")
        con.commit()


def _accessible_ids(con, project_id: int, analysis_ids: set[str]) -> set[str]:
    if not analysis_ids:
        return set()
    marks = ",".join("?" for _ in analysis_ids)
    rows = con.execute(
        f"""SELECT a.analysis_id FROM analysis_rows a
               JOIN project_dataset_links link ON link.dataset_id=a.dataset_id
               WHERE link.project_id=? AND a.analysis_id IN ({marks})""",
        [int(project_id), *sorted(analysis_ids)],
    ).fetchall()
    return {str(row["analysis_id"]) for row in rows}


def save_selection(
    project_id: int,
    *,
    name: str,
    analysis_ids: list[str] | tuple[str, ...] | set[str],
    note: str = "",
    context: dict | None = None,
) -> int:
    """Create or replace a named selection after checking the project scope."""
    ensure_selection_schema()
    label = str(name).strip()
    wanted = {str(value).strip() for value in analysis_ids if str(value).strip()}
    if not label:
        raise ValueError("Назовите рабочую выборку")
    if not wanted:
        raise ValueError("В рабочей выборке должна быть хотя бы одна точка")
    with connect() as con:
        available = _accessible_ids(con, int(project_id), wanted)
        missing = wanted - available
        if missing:
            raise ValueError("В выборке есть точки, недоступные активному проекту")
        now = _utcnow()
        con.execute(
            """INSERT INTO working_selections(project_id,name,note,context_json,created_at,updated_at)
               VALUES(?,?,?,?,?,?)
               ON CONFLICT(project_id,name) DO UPDATE SET
                 note=excluded.note, context_json=excluded.context_json, updated_at=excluded.updated_at""",
            (int(project_id), label, str(note).strip(), json.dumps(context or {}, ensure_ascii=False), now, now),
        )
        row = con.execute(
            "SELECT id FROM working_selections WHERE project_id=? AND name=?", (int(project_id), label)
        ).fetchone()
        selection_id = int(row["id"])
        con.execute("DELETE FROM working_selection_members WHERE selection_id=?", (selection_id,))
        con.executemany(
            "INSERT INTO working_selection_members(selection_id,analysis_id) VALUES(?,?)",
            [(selection_id, value) for value in sorted(available)],
        )
        con.commit()
    return selection_id


def list_selections(project_id: int) -> list[dict]:
    ensure_selection_schema()
    with connect() as con:
        rows = con.execute(
            """SELECT s.*, COUNT(m.analysis_id) AS member_count
               FROM working_selections s
               LEFT JOIN working_selection_members m ON m.selection_id=s.id
               WHERE s.project_id=? GROUP BY s.id ORDER BY s.updated_at DESC, s.id DESC""",
            (int(project_id),),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["context"] = json.loads(str(item.pop("context_json") or "{}"))
        except json.JSONDecodeError:
            item["context"] = {}
        result.append(item)
    return result


def selection_analysis_ids(selection_id: int) -> list[str]:
    ensure_selection_schema()
    with connect() as con:
        rows = con.execute(
            "SELECT analysis_id FROM working_selection_members WHERE selection_id=? ORDER BY analysis_id", (int(selection_id),)
        ).fetchall()
    return [str(row["analysis_id"]) for row in rows]


def delete_selection(selection_id: int) -> None:
    ensure_selection_schema()
    with connect() as con:
        con.execute("DELETE FROM working_selections WHERE id=?", (int(selection_id),))
        con.commit()
