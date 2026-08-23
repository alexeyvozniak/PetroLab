"""Small, project-scoped checklist for next analytical actions.

Checklist items deliberately describe a researcher's intent ("sort LA-ICP-MS
for 19 TR-1"), not a mutable property of an analysis.  Completing an item
therefore never edits source measurements or their QC state.
"""
from __future__ import annotations

from petrolab.db import _utcnow, connect


def ensure_project_checklist_schema() -> None:
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS project_checklist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                dataset_id INTEGER,
                target_route TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL,
                completed_at TEXT,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE SET NULL
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_project_checklist_status "
            "ON project_checklist_items(project_id, status, id DESC)"
        )
        con.commit()


def create_project_checklist_item(
    project_id: int,
    *,
    title: str,
    note: str = "",
    dataset_id: int | None = None,
    target_route: str = "",
) -> int:
    """Add a personal next step without changing any analytical record."""
    ensure_project_checklist_schema()
    clean_title = str(title).strip()
    if not clean_title:
        raise ValueError("Опишите, что нужно сделать")
    if len(clean_title) > 280:
        raise ValueError("Задача слишком длинная: сократите её до 280 символов")
    with connect() as con:
        project = con.execute("SELECT id FROM projects WHERE id=?", (int(project_id),)).fetchone()
        if project is None:
            raise ValueError("Проект не найден")
        clean_dataset_id = int(dataset_id) if dataset_id is not None else None
        if clean_dataset_id is not None:
            dataset = con.execute(
                """SELECT 1 FROM project_dataset_links
                   WHERE project_id=? AND dataset_id=? AND COALESCE(purpose, 'working') <> 'hidden'""",
                (int(project_id), clean_dataset_id),
            ).fetchone()
            if dataset is None:
                raise ValueError("Этот набор не входит в активный проект")
        cur = con.execute(
            """INSERT INTO project_checklist_items(
                project_id, title, note, dataset_id, target_route, status, created_at
            ) VALUES (?, ?, ?, ?, ?, 'open', ?)""",
            (
                int(project_id), clean_title, str(note).strip(), clean_dataset_id,
                str(target_route).strip(), _utcnow(),
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def list_project_checklist_items(project_id: int, *, completed: bool = False, limit: int | None = None) -> list[dict]:
    """Return active items or the compact completed history for one project."""
    ensure_project_checklist_schema()
    status = "done" if completed else "open"
    query = """
        SELECT item.*, dataset.name AS dataset_name, dataset.source_sheet AS dataset_sheet
        FROM project_checklist_items item
        LEFT JOIN datasets dataset ON dataset.id=item.dataset_id
        WHERE item.project_id=? AND item.status=?
        ORDER BY CASE WHEN item.status='open' THEN item.id END DESC,
                 completed_at DESC, item.id DESC
    """
    params: list[object] = [int(project_id), status]
    if limit is not None:
        query += " LIMIT ?"
        params.append(max(0, int(limit)))
    with connect() as con:
        rows = con.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def set_project_checklist_item_completed(project_id: int, item_id: int, *, completed: bool) -> bool:
    """Move an item between the active list and the reversible completed history."""
    ensure_project_checklist_schema()
    with connect() as con:
        cur = con.execute(
            """UPDATE project_checklist_items
               SET status=?, completed_at=?
               WHERE id=? AND project_id=?""",
            ("done" if completed else "open", _utcnow() if completed else None, int(item_id), int(project_id)),
        )
        con.commit()
    return cur.rowcount == 1
