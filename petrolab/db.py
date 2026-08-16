from __future__ import annotations

import csv
import hashlib
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pandas as pd

from petrolab.config import DATA_DIR

DB_PATH = DATA_DIR / "petrolab.sqlite3"
ASSETS_DIR = DATA_DIR / "assets"
LIBRARY_PROJECT_NAME = "Общая база PetroLab"
_LEGACY_LIBRARY_PROJECT_NAMES = (
    LIBRARY_PROJECT_NAME,
    "Общая библиотека анализов",
    "Общая библиотека",
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def init_db() -> None:
    with connect() as con:
        con.executescript(
            """
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                is_system INTEGER NOT NULL DEFAULT 0
            );

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
                source_path TEXT NOT NULL DEFAULT '',
                source_kind TEXT NOT NULL DEFAULT 'upload',
                header_row INTEGER NOT NULL DEFAULT 1,
                column_map_json TEXT NOT NULL DEFAULT '{}',
                sync_enabled INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS project_dataset_links (
                project_id INTEGER NOT NULL,
                dataset_id INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                added_at TEXT NOT NULL,
                purpose TEXT NOT NULL DEFAULT 'working',
                PRIMARY KEY(project_id, dataset_id),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS analysis_rows (
                analysis_id TEXT PRIMARY KEY,
                dataset_id INTEGER NOT NULL,
                row_index INTEGER NOT NULL,
                source_row INTEGER,
                data_json TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE(dataset_id, row_index),
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS formula_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id TEXT NOT NULL,
                dataset_id INTEGER NOT NULL,
                mineral_key TEXT NOT NULL,
                method_id TEXT NOT NULL,
                method_title TEXT NOT NULL,
                source_fingerprint TEXT NOT NULL,
                result_json TEXT NOT NULL,
                derived_columns_json TEXT NOT NULL,
                calculated_at TEXT NOT NULL,
                is_current INTEGER NOT NULL DEFAULT 1,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_analysis_rows_dataset ON analysis_rows(dataset_id);
            CREATE INDEX IF NOT EXISTS idx_formula_results_dataset ON formula_results(dataset_id);
            CREATE INDEX IF NOT EXISTS idx_formula_results_analysis ON formula_results(analysis_id);
            CREATE INDEX IF NOT EXISTS idx_project_dataset_links_dataset ON project_dataset_links(dataset_id);

            CREATE TABLE IF NOT EXISTS image_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                dataset_id INTEGER NOT NULL,
                analysis_id TEXT,
                scope_type TEXT NOT NULL,
                scope_column TEXT NOT NULL DEFAULT '',
                scope_value TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                original_filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_image_assets_dataset ON image_assets(dataset_id);
            CREATE INDEX IF NOT EXISTS idx_image_assets_analysis ON image_assets(analysis_id);
            CREATE INDEX IF NOT EXISTS idx_image_assets_project ON image_assets(project_id);

            CREATE TABLE IF NOT EXISTS change_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                dataset_id INTEGER NOT NULL,
                analysis_id TEXT NOT NULL,
                source_row INTEGER,
                column_name TEXT NOT NULL,
                old_value TEXT,
                new_value TEXT,
                changed_at TEXT NOT NULL,
                sync_status TEXT NOT NULL DEFAULT 'local',
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_change_log_project ON change_log(project_id);
            CREATE INDEX IF NOT EXISTS idx_change_log_dataset ON change_log(dataset_id);
            """
        )
        project_columns = {row[1] for row in con.execute("PRAGMA table_info(projects)").fetchall()}
        if "is_system" not in project_columns:
            con.execute("ALTER TABLE projects ADD COLUMN is_system INTEGER NOT NULL DEFAULT 0")
        columns = {row[1] for row in con.execute("PRAGMA table_info(datasets)").fetchall()}
        migrations = {
            "source_path": "TEXT NOT NULL DEFAULT ''",
            "source_kind": "TEXT NOT NULL DEFAULT 'upload'",
            "header_row": "INTEGER NOT NULL DEFAULT 1",
            "column_map_json": "TEXT NOT NULL DEFAULT '{}'",
            "sync_enabled": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, ddl in migrations.items():
            if name not in columns:
                con.execute(f"ALTER TABLE datasets ADD COLUMN {name} {ddl}")
        image_columns = {row[1] for row in con.execute("PRAGMA table_info(image_assets)").fetchall()}
        image_migrations = {
            "scope_type": "TEXT NOT NULL DEFAULT 'Точки анализа'",
            "scope_column": "TEXT NOT NULL DEFAULT ''",
            "scope_value": "TEXT NOT NULL DEFAULT ''",
        }
        for name, ddl in image_migrations.items():
            if name not in image_columns:
                con.execute(f"ALTER TABLE image_assets ADD COLUMN {name} {ddl}")
        # Existing installations predate the many-to-many project membership.
        # Backfill one membership from the legacy datasets.project_id owner.
        con.execute(
            """
            INSERT OR IGNORE INTO project_dataset_links(project_id, dataset_id, note, added_at, purpose)
            SELECT project_id, id, 'Перенесено из прежней структуры', imported_at, 'working'
            FROM datasets
            """
        )
        con.commit()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_bytes(path: str | Path, payload: bytes) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{target.name}.", dir=str(target.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, target)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def atomic_write_csv(path: str | Path, dataframe: pd.DataFrame) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".csv", dir=str(target.parent))
    os.close(fd)
    try:
        dataframe.to_csv(temp_path, index=False, quoting=csv.QUOTE_MINIMAL)
        os.replace(temp_path, target)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def list_projects(*, include_system: bool = False) -> list[dict]:
    with connect() as con:
        query = "SELECT * FROM projects"
        if not include_system:
            query += " WHERE COALESCE(is_system, 0)=0"
        rows = con.execute(query + " ORDER BY created_at DESC").fetchall()
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


def get_or_create_library_project() -> int:
    """Return the hidden root that owns shared raw data, never an article project."""
    with connect() as con:
        placeholders = ", ".join("?" for _ in _LEGACY_LIBRARY_PROJECT_NAMES)
        row = con.execute(
            f"SELECT id FROM projects WHERE name IN ({placeholders}) ORDER BY id LIMIT 1",
            _LEGACY_LIBRARY_PROJECT_NAMES,
        ).fetchone()
        if row:
            con.execute("UPDATE projects SET is_system=1 WHERE id=?", (int(row["id"]),))
            con.commit()
            return int(row["id"])
        cur = con.execute(
            "INSERT INTO projects(name, description, created_at, is_system) VALUES (?, ?, ?, 1)",
            (
                LIBRARY_PROJECT_NAME,
                "Системный корень общей базы. Рабочие проекты подключают данные ссылками без копирования.",
                _utcnow(),
            ),
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


def list_accessible_datasets(project_id: int, *, include_provenance: bool = False) -> list[dict]:
    """Return datasets included in a project's normal working context.

    ``project_dataset_links`` is the many-to-many membership layer. Fully
    resolved mixed-source containers can remain linked with ``purpose='provenance'``
    so their original snapshot stays recoverable without cluttering ordinary
    selectors. Pass ``include_provenance=True`` only for provenance/audit views.
    """
    with connect() as con:
        where = "WHERE l.project_id=?"
        params: list[object] = [int(project_id), int(project_id)]
        if not include_provenance:
            where += " AND COALESCE(l.purpose, 'working') <> 'provenance'"
        rows = con.execute(
            f"""
            SELECT d.*, p.name AS project_name,
                   CASE WHEN d.project_id=? THEN 0 ELSE 1 END AS linked_to_project,
                   l.purpose AS membership_purpose, l.note AS membership_note
            FROM project_dataset_links l
            JOIN datasets d ON d.id=l.dataset_id
            JOIN projects p ON p.id=d.project_id
            {where}
            ORDER BY imported_at DESC
            """,
            params,
        ).fetchall()
    return [dict(row) for row in rows]


def dataset_is_accessible(project_id: int, dataset_id: int) -> bool:
    """Whether a dataset is part of this project's context, including provenance-only links."""
    with connect() as con:
        row = con.execute(
            "SELECT 1 FROM project_dataset_links WHERE project_id=? AND dataset_id=?",
            (int(project_id), int(dataset_id)),
        ).fetchone()
    return row is not None


def link_dataset_to_project(
    project_id: int,
    dataset_id: int,
    note: str = "",
    *,
    purpose: str = "working",
) -> None:
    """Add a project membership without copying or mutating the raw dataset."""
    with connect() as con:
        dataset = con.execute("SELECT id FROM datasets WHERE id=?", (int(dataset_id),)).fetchone()
        project = con.execute("SELECT id FROM projects WHERE id=?", (int(project_id),)).fetchone()
        if dataset is None or project is None:
            raise ValueError("Проект или набор данных не найден")
        con.execute(
            """
            INSERT INTO project_dataset_links(project_id, dataset_id, note, added_at, purpose)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(project_id, dataset_id) DO UPDATE SET
                note=excluded.note, purpose=excluded.purpose
            """,
            (int(project_id), int(dataset_id), str(note).strip(), _utcnow(), str(purpose).strip() or "working"),
        )
        con.commit()


def unlink_dataset_from_project(project_id: int, dataset_id: int) -> None:
    with connect() as con:
        con.execute(
            "DELETE FROM project_dataset_links WHERE project_id=? AND dataset_id=?",
            (int(project_id), int(dataset_id)),
        )
        con.commit()


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
        dataset_id = int(cur.lastrowid)
        con.execute(
            """
            INSERT OR IGNORE INTO project_dataset_links(project_id, dataset_id, note, added_at, purpose)
            VALUES (?, ?, ?, ?, 'working')
            """,
            (int(project_id), dataset_id, "Создано вместе с набором", _utcnow()),
        )
        con.commit()
        return dataset_id


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
            by_source = {r["source_row"]: r["analysis_id"] for r in existing if r["source_row"] is not None}
            all_old_ids = {r["analysis_id"] for r in existing}

            planned = []
            reused_ids: set[str] = set()
            for i, (_, row) in enumerate(df.iterrows()):
                source_row = source_rows[i]
                analysis_id = by_source.get(source_row, uuid4().hex)
                if analysis_id in all_old_ids:
                    reused_ids.add(analysis_id)
                data = _json_safe_record(row.to_dict())
                planned.append((analysis_id, i, source_row, json.dumps(data, ensure_ascii=False)))

            removed_ids = all_old_ids - reused_ids
            if removed_ids:
                marks = ",".join("?" for _ in removed_ids)
                con.execute(f"UPDATE image_assets SET analysis_id=NULL WHERE analysis_id IN ({marks})", list(removed_ids))
                con.execute(f"DELETE FROM analysis_rows WHERE analysis_id IN ({marks})", list(removed_ids))

            con.execute(
                "UPDATE analysis_rows SET row_index = -1000000 - row_index WHERE dataset_id=?",
                (dataset_id,),
            )

            for analysis_id, row_index, source_row, data_json in planned:
                if analysis_id in reused_ids:
                    con.execute(
                        """
                        UPDATE analysis_rows
                        SET row_index=?, source_row=?, data_json=?, updated_at=?
                        WHERE analysis_id=?
                        """,
                        (row_index, source_row, data_json, now, analysis_id),
                    )
                else:
                    con.execute(
                        """
                        INSERT INTO analysis_rows(analysis_id, dataset_id, row_index, source_row, data_json, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (analysis_id, dataset_id, row_index, source_row, data_json, now),
                    )
        else:
            con.execute(
                "UPDATE image_assets SET analysis_id=NULL WHERE analysis_id IN "
                "(SELECT analysis_id FROM analysis_rows WHERE dataset_id=?)",
                (dataset_id,),
            )
            con.execute("DELETE FROM analysis_rows WHERE dataset_id=?", (dataset_id,))
            payload = []
            for i, (_, row) in enumerate(df.iterrows()):
                data = _json_safe_record(row.to_dict())
                payload.append((uuid4().hex, dataset_id, i, source_rows[i], json.dumps(data, ensure_ascii=False), now))
            con.executemany(
                """
                INSERT INTO analysis_rows(analysis_id, dataset_id, row_index, source_row, data_json, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                payload,
            )

        con.execute("UPDATE datasets SET row_count=? WHERE id=?", (len(df), dataset_id))
        con.commit()


def ensure_dataset_rows(dataset_id: int) -> None:
    with connect() as con:
        count = con.execute("SELECT COUNT(*) FROM analysis_rows WHERE dataset_id=?", (dataset_id,)).fetchone()[0]
    if count:
        return
    dataset = get_dataset(dataset_id)
    csv_path = Path(dataset["csv_path"])
    if not csv_path.exists():
        return
    df = pd.read_csv(csv_path)
    header_row = int(dataset.get("header_row") or 1)
    source_rows = list(range(header_row + 1, header_row + 1 + len(df)))
    replace_dataset_rows(dataset_id, df, source_rows=source_rows)


def load_dataset_dataframe(dataset_id: int, include_meta: bool = True) -> pd.DataFrame:
    ensure_dataset_rows(dataset_id)
    dataset = get_dataset(dataset_id)
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM analysis_rows WHERE dataset_id=? ORDER BY row_index",
            (dataset_id,),
        ).fetchall()
    records = []
    for r in rows:
        data = json.loads(r["data_json"])
        if include_meta:
            data = {
                "_analysis_id": r["analysis_id"],
                "_dataset_id": dataset_id,
                "_project_id": dataset["project_id"],
                "_row_index": r["row_index"],
                "_source_row": r["source_row"],
                **data,
            }
        records.append(data)
    return pd.DataFrame(records)


def load_unified_analyses(project_id: int | None = None, dataset_ids: list[int] | None = None) -> pd.DataFrame:
    datasets = list_datasets(project_id)
    if dataset_ids is not None:
        wanted = set(int(x) for x in dataset_ids)
        datasets = [d for d in datasets if int(d["id"]) in wanted]
    frames = []
    for d in datasets:
        df = load_dataset_dataframe(int(d["id"]), include_meta=True)
        if not df.empty:
            df["Проект"] = d["project_name"]
            df["Набор"] = d["name"]
            df["Минерал"] = d["mineral_key"]
            frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def hash_dataframe(df: pd.DataFrame) -> str:
    payload = df.to_csv(index=False, na_rep="").encode("utf-8")
    return _sha256_bytes(payload)


def serialize_cell(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if pd.isna(value):
        return None
    return json.dumps(value, ensure_ascii=False, default=str)


def deserialize_cell(value: str | None):
    if value is None:
        return None
    return json.loads(value)


def log_change(
    con: sqlite3.Connection,
    project_id: int,
    dataset_id: int,
    analysis_id: str,
    source_row: int | None,
    column_name: str,
    old_value,
    new_value,
    sync_status: str = "local",
) -> None:
    con.execute(
        """
        INSERT INTO change_log(project_id, dataset_id, analysis_id, source_row, column_name, old_value, new_value, changed_at, sync_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            project_id,
            dataset_id,
            analysis_id,
            source_row,
            column_name,
            serialize_cell(old_value),
            serialize_cell(new_value),
            _utcnow(),
            sync_status,
        ),
    )


def count_pending_sync(dataset_id: int) -> int:
    with connect() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM change_log WHERE dataset_id=? AND sync_status='local'",
            (dataset_id,),
        ).fetchone()
    return int(row["n"])


def list_changes(project_id: int | None = None, limit: int = 500) -> list[dict]:
    with connect() as con:
        if project_id is None:
            rows = con.execute(
                """
                SELECT c.*, d.name AS dataset_name, p.name AS project_name
                FROM change_log c
                JOIN datasets d ON d.id=c.dataset_id
                JOIN projects p ON p.id=c.project_id
                ORDER BY c.changed_at DESC, c.id DESC LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT c.*, d.name AS dataset_name, p.name AS project_name
                FROM change_log c
                JOIN datasets d ON d.id=c.dataset_id
                JOIN projects p ON p.id=c.project_id
                WHERE c.project_id=? ORDER BY c.changed_at DESC, c.id DESC LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()
    return [dict(r) for r in rows]


def update_sync_status(change_ids: list[int], status: str) -> None:
    if not change_ids:
        return
    with connect() as con:
        con.executemany(
            "UPDATE change_log SET sync_status=? WHERE id=?",
            [(status, int(cid)) for cid in change_ids],
        )
        con.commit()
