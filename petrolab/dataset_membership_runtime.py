from __future__ import annotations

import sqlite3

from . import db as _db


_ORIGINAL_ENSURE_STORAGE = _db.ensure_storage
_ORIGINAL_LINK = _db.link_dataset_to_project


def _ensure_tombstones() -> None:
    _db.DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(_db.DB_PATH) as con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS project_dataset_unlinks (
                project_id INTEGER NOT NULL,
                dataset_id INTEGER NOT NULL,
                removed_at TEXT NOT NULL,
                PRIMARY KEY(project_id, dataset_id),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            """
            DELETE FROM project_dataset_links
            WHERE EXISTS (
                SELECT 1 FROM project_dataset_unlinks u
                WHERE u.project_id=project_dataset_links.project_id
                  AND u.dataset_id=project_dataset_links.dataset_id
            )
            """
        )
        con.commit()


def ensure_storage() -> None:
    """Run legacy migrations, then preserve explicit project-level removals.

    Older storage code repopulates owner-project memberships on every connection.
    A persistent unlink tombstone turns that historical migration into harmless
    idempotent compatibility behavior without deleting the global dataset itself.
    """
    _ORIGINAL_ENSURE_STORAGE()
    _ensure_tombstones()


def unlink_dataset_from_project(project_id: int, dataset_id: int) -> None:
    ensure_storage()
    with sqlite3.connect(_db.DB_PATH) as con:
        con.execute("PRAGMA foreign_keys=ON")
        project = con.execute("SELECT id FROM projects WHERE id=?", (int(project_id),)).fetchone()
        dataset = con.execute("SELECT id FROM datasets WHERE id=?", (int(dataset_id),)).fetchone()
        if project is None or dataset is None:
            return
        con.execute(
            """
            INSERT INTO project_dataset_unlinks(project_id, dataset_id, removed_at)
            VALUES (?, ?, ?)
            ON CONFLICT(project_id, dataset_id) DO UPDATE SET removed_at=excluded.removed_at
            """,
            (int(project_id), int(dataset_id), _db._utcnow()),
        )
        con.execute(
            "DELETE FROM project_dataset_links WHERE project_id=? AND dataset_id=?",
            (int(project_id), int(dataset_id)),
        )
        con.commit()


def link_dataset_to_project(
    project_id: int,
    dataset_id: int,
    note: str = "",
    *,
    purpose: str = "working",
) -> None:
    """Explicit relink clears a previous unlink tombstone."""
    ensure_storage()
    with sqlite3.connect(_db.DB_PATH) as con:
        con.execute(
            "DELETE FROM project_dataset_unlinks WHERE project_id=? AND dataset_id=?",
            (int(project_id), int(dataset_id)),
        )
        con.commit()
    _ORIGINAL_LINK(
        int(project_id),
        int(dataset_id),
        str(note),
        purpose=str(purpose),
    )


def install() -> None:
    _db.ensure_storage = ensure_storage
    _db.unlink_dataset_from_project = unlink_dataset_from_project
    _db.link_dataset_to_project = link_dataset_to_project
