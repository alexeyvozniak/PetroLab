from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

APP_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("PETROLAB_DATA_DIR", str(APP_DIR / "petrolab_data"))).expanduser().resolve()
DB_PATH = DATA_DIR / "petrolab.sqlite3"
ASSETS_DIR = DATA_DIR / "assets"
BACKUPS_DIR = DATA_DIR / "backups"

DATASET_EXTRA_COLUMNS = {
    "source_path": "TEXT NOT NULL DEFAULT ''",
    "source_kind": "TEXT NOT NULL DEFAULT 'upload'",
    "header_row": "INTEGER NOT NULL DEFAULT 1",
    "column_map_json": "TEXT NOT NULL DEFAULT '{}'",
    "sync_enabled": "INTEGER NOT NULL DEFAULT 0",
}

META_COLUMNS = {
    "_analysis_id", "_dataset_id", "_project_id", "_row_index", "_source_row",
    "Проект", "Набор", "Минерал", "Источник", "Лист", "Строка Excel",
}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS datasets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                mineral_key TEXT NOT NULL,
                source_filename TEXT NOT NULL,
                source_sheet TEXT NOT NULL DEFAULT '',
                source_sha256 TEXT NOT NULL,
                csv_path TEXT NOT NULL,
                row_count INTEGER NOT NULL,
                imported_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
            """
        )
        existing = _table_columns(con, "datasets")
        for col, ddl in DATASET_EXTRA_COLUMNS.items():
            if col not in existing:
                con.execute(f"ALTER TABLE datasets ADD COLUMN {col} {ddl}")

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_rows (
                analysis_id TEXT PRIMARY KEY,
                dataset_id INTEGER NOT NULL,
                row_index INTEGER NOT NULL,
                source_row INTEGER,
                data_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                UNIQUE(dataset_id, row_index)
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_analysis_dataset ON analysis_rows(dataset_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_analysis_source_row ON analysis_rows(dataset_id, source_row)")

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS image_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                dataset_id INTEGER,
                analysis_id TEXT,
                scope_type TEXT NOT NULL DEFAULT 'dataset',
                scope_column TEXT NOT NULL DEFAULT '',
                scope_value TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL DEFAULT 'BSE/EDS/Фото',
                title TEXT NOT NULL DEFAULT '',
                original_filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                added_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id),
                FOREIGN KEY(dataset_id) REFERENCES datasets(id),
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE SET NULL
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_images_dataset ON image_assets(dataset_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_images_analysis ON image_assets(analysis_id)")

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS change_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id INTEGER NOT NULL,
                analysis_id TEXT,
                column_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                synced_to_source INTEGER NOT NULL DEFAULT 0,
                source_backup TEXT NOT NULL DEFAULT '',
                changed_at TEXT NOT NULL,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id)
            )
            """
        )

        con.execute(
            """
            CREATE TABLE IF NOT EXISTS plot_recipes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                name TEXT NOT NULL,
                config_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id, name),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS style_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                name TEXT NOT NULL,
                grouping_column TEXT NOT NULL DEFAULT '',
                styles_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(project_id, name),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        con.commit()
    finally:
        con.close()


@contextmanager
def connect():
    ensure_storage()
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
    finally:
        con.close()


def list_projects() -> list[dict]:
    with connect() as con:
        rows = con.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
    return [dict(r) for r in rows]


def create_project(name: str, description: str = "") -> int:
    name = name.strip()
    if not name:
        raise ValueError("Название проекта не может быть пустым")
    with connect() as con:
        cur = con.execute(
            "INSERT INTO projects(name, description, created_at) VALUES (?, ?, ?)",
            (name, description.strip(), _utcnow()),
        )
        con.commit()
        return int(cur.lastrowid)


def list_datasets(project_id: int | None = None) -> list[dict]:
    with connect() as con:
        if project_id is None:
            rows = con.execute(
                """
                SELECT d.*, p.name AS project_name
                FROM datasets d JOIN projects p ON p.id=d.project_id
                ORDER BY d.imported_at DESC
                """
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT d.*, p.name AS project_name
                FROM datasets d JOIN projects p ON p.id=d.project_id
                WHERE d.project_id=? ORDER BY d.imported_at DESC
                """,
                (project_id,),
            ).fetchall()
    return [dict(r) for r in rows]


def get_dataset(dataset_id: int) -> dict:
    with connect() as con:
        row = con.execute(
            """
            SELECT d.*, p.name AS project_name
            FROM datasets d JOIN projects p ON p.id=d.project_id
            WHERE d.id=?
            """,
            (dataset_id,),
        ).fetchone()
    if not row:
        raise KeyError(f"Набор данных {dataset_id} не найден")
    return dict(row)


def add_dataset(
    project_id: int,
    name: str,
    mineral_key: str,
    source_filename: str,
    source_sheet: str,
    source_sha256: str,
    csv_path: str,
    row_count: int,
    source_path: str = "",
    source_kind: str = "upload",
    header_row: int = 1,
    column_map: dict | None = None,
    sync_enabled: bool = False,
) -> int:
    with connect() as con:
        cur = con.execute(
            """
            INSERT INTO datasets(
                project_id, name, mineral_key, source_filename, source_sheet,
                source_sha256, csv_path, row_count, imported_at,
                source_path, source_kind, header_row, column_map_json, sync_enabled
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)      
            """,
            (
                project_id, name.strip(), mineral_key, source_filename, source_sheet,
                source_sha256, csv_path, int(row_count), _utcnow(), source_path,
                source_kind, int(header_row), json.dumps(column_map or {}, ensure_ascii=False),
                1 if sync_enabled else 0,
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def update_dataset_metadata(dataset_id: int, **fields) -> None:
    allowed = {
        "source_sha256", "row_count", "column_map_json", "source_path", "source_filename",
        "source_sheet", "header_row", "sync_enabled", "name", "mineral_key",
    }
    clean = {k: v for k, v in fields.items() if k in allowed}
    if not clean:
        return
    if "column_map_json" in clean and isinstance(clean["column_map_json"], dict):
        clean["column_map_json"] = json.dumps(clean["column_map_json"], ensure_ascii=False)
    if "sync_enabled" in clean:
        clean["sync_enabled"] = 1 if clean["sync_enabled"] else 0
    assignments = ", ".join(f"{k}=?" for k in clean)
    values = list(clean.values()) + [dataset_id]
    with connect() as con:
        con.execute(f"UPDATE datasets SET {assignments} WHERE id=?", values)
        con.commit()


def update_source_hash_for_path(source_path: str, source_sha256: str) -> None:
    if not source_path:
        return
    with connect() as con:
        con.execute(
            "UPDATE datasets SET source_sha256=? WHERE source_path=?",
            (source_sha256, source_path),
        )
        con.commit()


def _json_safe_record(record: dict) -> dict:
    out = {}
    for key, value in record.items():
        if pd.isna(value) if not isinstance(value, (list, dict, tuple)) else False:
            out[key] = None
        elif hasattr(value, "item"):
            out[key] = value.item()
        elif isinstance(value, pd.Timestamp):
            out[key] = value.isoformat()
        else:
            out[key] = value
    return out


def replace_dataset_rows(
    dataset_id: int,
    df: pd.DataFrame,
    source_rows: list[int | None] | None = None,
    preserve_ids_by_source_row: bool = False,
) -> None:
    source_rows = source_rows or [None] * len(df)
    if len(source_rows) != len(df):
        raise ValueError("Количество source_rows не совпадает с числом строк")
    now = _utcnow()

    with connect() as con:
        if preserve_ids_by_source_row:
            existing = con.execute(
                "SELECT analysis_id, source_row, row_index FROM analysis_rows WHERE dataset_id=?",
                (dataset_id,),
            ).fetchall()
            by_source = {r["source_row"]: r[