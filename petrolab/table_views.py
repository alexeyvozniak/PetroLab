from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from petrolab.db import connect


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_table() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS table_views (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                scope_key TEXT NOT NULL,
                name TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id, scope_key, name),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_table_views_project_scope "
            "ON table_views(project_id, scope_key)"
        )
        con.commit()


def list_table_views(project_id: int, scope_key: str) -> list[dict[str, Any]]:
    _ensure_table()
    with connect() as con:
        rows = con.execute(
            """
            SELECT id, project_id, scope_key, name, config_json, created_at, updated_at
            FROM table_views
            WHERE project_id=? AND scope_key=?
            ORDER BY name COLLATE NOCASE, id
            """,
            (int(project_id), str(scope_key)),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        try:
            item["config"] = json.loads(str(item.pop("config_json")))
        except (TypeError, ValueError, json.JSONDecodeError):
            item["config"] = {}
        result.append(item)
    return result


def save_table_view(
    project_id: int,
    scope_key: str,
    name: str,
    config: dict[str, Any],
) -> int:
    _ensure_table()
    clean_name = " ".join(str(name or "").split()).strip()
    if not clean_name:
        raise ValueError("View name must not be empty")
    now = _utcnow()
    payload = json.dumps(config, ensure_ascii=False, sort_keys=True)
    with connect() as con:
        existing = con.execute(
            "SELECT id FROM table_views WHERE project_id=? AND scope_key=? AND name=?",
            (int(project_id), str(scope_key), clean_name),
        ).fetchone()
        if existing is None:
            cursor = con.execute(
                """
                INSERT INTO table_views(project_id, scope_key, name, config_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (int(project_id), str(scope_key), clean_name, payload, now, now),
            )
            view_id = int(cursor.lastrowid)
        else:
            view_id = int(existing["id"])
            con.execute(
                "UPDATE table_views SET config_json=?, updated_at=? WHERE id=?",
                (payload, now, view_id),
            )
        con.commit()
    return view_id


def delete_table_view(project_id: int, scope_key: str, name: str) -> bool:
    _ensure_table()
    with connect() as con:
        cursor = con.execute(
            "DELETE FROM table_views WHERE project_id=? AND scope_key=? AND name=?",
            (int(project_id), str(scope_key), str(name)),
        )
        con.commit()
        return bool(cursor.rowcount)
