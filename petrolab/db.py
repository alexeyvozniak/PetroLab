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

# Raw observations live in one database.  Projects are working contexts that
# reference those observations; this system row is intentionally hidden from
# the project picker.
LIBRARY_PROJECT_NAME = "Общая база"
_LEGACY_LIBRARY_PROJECT_NAMES = ("Общая база", "Общая библиотека")

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
    with sqlite3.connect(DB_PATH) as con:
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
        project_columns = _table_columns(con, "projects")
        if "is_system" not in project_columns:
            con.execute("ALTER TABLE projects ADD COLUMN is_system INTEGER NOT NULL DEFAULT 0")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS project_dataset_links (
                project_id INTEGER NOT NULL,
                dataset_id INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                added_at TEXT NOT NULL,
                PRIMARY KEY(project_id, dataset_id),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_project_dataset_links_dataset ON project_dataset_links(dataset_id)")
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

        link_columns = _table_columns(con, "project_dataset_links")
        if "purpose" not in link_columns:
            con.execute(
                "ALTER TABLE project_dataset_links ADD COLUMN purpose TEXT NOT NULL DEFAULT 'working'"
            )
        # Existing project-owned datasets remain visible in their former project.
        # From this migration forward this row is a membership, not ownership.
        con.execute(
            """
            INSERT OR IGNORE INTO project_dataset_links(project_id, dataset_id, note, added_at, purpose)
            SELECT project_id, id, 'Автоматически добавлено при переходе на общую базу', ?, 'working'
            FROM datasets
            """,
            (_utcnow(),),
        )

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
        con.execute("""CREATE TABLE IF NOT EXISTS composition_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, rock_id INTEGER,
            name TEXT NOT NULL, kind TEXT NOT NULL, values_json TEXT NOT NULL,
            units_json TEXT NOT NULL DEFAULT '{}', provenance_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_composition_sets_project ON composition_sets(project_id)")
        con.execute("""CREATE TABLE IF NOT EXISTS assemblages (
            id INTEGER PRIMARY KEY AUTOINCREMENT, project_id INTEGER NOT NULL, name TEXT NOT NULL,
            equilibrium_status TEXT NOT NULL DEFAULT 'unreviewed', note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE)""")
        con.execute("""CREATE TABLE IF NOT EXISTS assemblage_members (
            assemblage_id INTEGER NOT NULL, analysis_id TEXT NOT NULL, phase TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT '', generation TEXT NOT NULL DEFAULT '',
            pair_group TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(assemblage_id, analysis_id),
            FOREIGN KEY(assemblage_id) REFERENCES assemblages(id) ON DELETE CASCADE,
            FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE)""")
        con.execute("CREATE INDEX IF NOT EXISTS idx_assemblage_members_analysis ON assemblage_members(analysis_id)")
        con.commit()


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


def list_accessible_datasets(project_id: int) -> list[dict]:
    """Return datasets included in a project's working context.

    The dataset row is global; ``project_dataset_links`` is the many-to-many
    membership layer.  ``project_id`` on datasets remains provenance for older
    installations and source attribution, not an exclusivity boundary.
    """
    with connect() as con:
        rows = con.execute(
            """
            SELECT d.*, p.name AS project_name,
                   CASE WHEN d.project_id=? THEN 0 ELSE 1 END AS linked_to_project,
                   l.purpose AS membership_purpose, l.note AS membership_note
            FROM project_dataset_links l
            JOIN datasets d ON d.id=l.dataset_id
            JOIN projects p ON p.id=d.project_id
            WHERE l.project_id=?
            ORDER BY imported_at DESC
            """,
            (int(project_id), int(project_id)),
        ).fetchall()
    return [dict(row) for row in rows]


def dataset_is_accessible(project_id: int, dataset_id: int) -> bool:
    """Whether a dataset is part of this project's working context."""
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
        # A new global row always starts with one explicit membership.  This
        # keeps direct API callers and imported datasets consistent with the
        # many-to-many project context model.
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
        if df.empty:
            continue
        df.insert(5 if len(df.columns) >= 5 else len(df.columns), "Проект", d["project_name"])
        df.insert(6 if len(df.columns) >= 6 else len(df.columns), "Набор", d["name"])
        df.insert(7 if len(df.columns) >= 7 else len(df.columns), "Минерал", d["mineral_key"])
        df.insert(8 if len(df.columns) >= 8 else len(df.columns), "Источник", d["source_filename"])
        df.insert(9 if len(df.columns) >= 9 else len(df.columns), "Лист", d["source_sheet"])
        df.insert(10 if len(df.columns) >= 10 else len(df.columns), "Строка Excel", df["_source_row"])
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def get_analysis_record(analysis_id: str) -> dict:
    with connect() as con:
        row = con.execute(
            """
            SELECT a.*, d.name AS dataset_name, d.project_id, d.mineral_key, d.source_filename,
                   d.source_sheet, p.name AS project_name
            FROM analysis_rows a
            JOIN datasets d ON d.id=a.dataset_id
            JOIN projects p ON p.id=d.project_id
            WHERE a.analysis_id=?
            """,
            (analysis_id,),
        ).fetchone()
    if not row:
        raise KeyError("Анализ не найден")
    out = dict(row)
    out["data"] = json.loads(out.pop("data_json"))
    return out


def update_analysis_values(changes: list[dict], synced_to_source: bool = False, source_backup: str = "") -> None:
    if not changes:
        return
    now = _utcnow()
    grouped: dict[str, list[dict]] = {}
    for ch in changes:
        grouped.setdefault(ch["analysis_id"], []).append(ch)
    with connect() as con:
        for analysis_id, items in grouped.items():
            row = con.execute("SELECT data_json FROM analysis_rows WHERE analysis_id=?", (analysis_id,)).fetchone()
            if not row:
                continue
            data = json.loads(row["data_json"])
            for ch in items:
                data[ch["column_name"]] = ch["new_value"]
                con.execute(
                    """
                    INSERT INTO change_log(dataset_id, analysis_id, column_name, old_value, new_value,
                                           synced_to_source, source_backup, changed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ch["dataset_id"], analysis_id, ch["column_name"],
                        None if ch["old_value"] is None else str(ch["old_value"]),
                        None if ch["new_value"] is None else str(ch["new_value"]),
                        1 if synced_to_source else 0, source_backup, now,
                    ),
                )
            con.execute(
                "UPDATE analysis_rows SET data_json=?, updated_at=? WHERE analysis_id=?",
                (json.dumps(_json_safe_record(data), ensure_ascii=False), now, analysis_id),
            )
        con.commit()


def list_change_log(dataset_id: int | None = None, limit: int = 500) -> list[dict]:
    with connect() as con:
        if dataset_id is None:
            rows = con.execute(
                "SELECT * FROM change_log ORDER BY id DESC LIMIT ?", (int(limit),)
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM change_log WHERE dataset_id=? ORDER BY id DESC LIMIT ?",
                (dataset_id, int(limit)),
            ).fetchall()
    return [dict(r) for r in rows]


def add_image_asset(
    project_id: int,
    dataset_id: int | None,
    analysis_id: str | None,
    scope_type: str,
    scope_column: str,
    scope_value: str,
    kind: str,
    title: str,
    original_filename: str,
    stored_path: str,
) -> int:
    with connect() as con:
        cur = con.execute(
            """
            INSERT INTO image_assets(project_id, dataset_id, analysis_id, scope_type, scope_column, scope_value,
                                     kind, title, original_filename, stored_path, added_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id, dataset_id, analysis_id, scope_type, scope_column, scope_value,
                kind, title, original_filename, stored_path, _utcnow(),
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def list_image_assets(project_id: int | None = None, dataset_id: int | None = None, analysis_id: str | None = None) -> list[dict]:
    clauses = []
    params: list = []
    if project_id is not None:
        clauses.append("i.project_id=?")
        params.append(project_id)
    if dataset_id is not None:
        clauses.append("i.dataset_id=?")
        params.append(dataset_id)
    if analysis_id is not None:
        clauses.append("i.analysis_id=?")
        params.append(analysis_id)
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as con:
        rows = con.execute(
            f"""
            SELECT i.*, d.name AS dataset_name, p.name AS project_name
            FROM image_assets i
            LEFT JOIN datasets d ON d.id=i.dataset_id
            JOIN projects p ON p.id=i.project_id
            {where}
            ORDER BY i.added_at DESC
            """,
            params,
        ).fetchall()
    return [dict(r) for r in rows]


def delete_image_asset(asset_id: int) -> None:
    with connect() as con:
        row = con.execute("SELECT stored_path FROM image_assets WHERE id=?", (asset_id,)).fetchone()
        con.execute("DELETE FROM image_assets WHERE id=?", (asset_id,))
        con.commit()
    if row:
        try:
            Path(row["stored_path"]).unlink(missing_ok=True)
        except OSError:
            pass


def save_plot_recipe(name: str, config: dict, project_id: int | None = None) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Название рецепта не может быть пустым")
    now = _utcnow()
    payload = json.dumps(config, ensure_ascii=False)
    with connect() as con:
        existing = con.execute(
            "SELECT id FROM plot_recipes WHERE project_id IS ? AND name=?",
            (project_id, name),
        ).fetchone()
        if existing:
            con.execute(
                "UPDATE plot_recipes SET config_json=?, updated_at=? WHERE id=?",
                (payload, now, existing["id"]),
            )
            con.commit()
            return int(existing["id"])
        cur = con.execute(
            "INSERT INTO plot_recipes(project_id, name, config_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (project_id, name, payload, now, now),
        )
        con.commit()
        return int(cur.lastrowid)


def list_plot_recipes(project_id: int | None = None) -> list[dict]:
    with connect() as con:
        if project_id is None:
            rows = con.execute("SELECT * FROM plot_recipes ORDER BY updated_at DESC, name").fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM plot_recipes WHERE project_id IS NULL OR project_id=? ORDER BY updated_at DESC, name",
                (project_id,),
            ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["config"] = json.loads(d.pop("config_json"))
        out.append(d)
    return out


def delete_plot_recipe(recipe_id: int) -> None:
    with connect() as con:
        con.execute("DELETE FROM plot_recipes WHERE id=?", (recipe_id,))
        con.commit()


def save_style_profile(name: str, grouping_column: str, styles: dict, project_id: int | None = None) -> int:
    name = name.strip()
    if not name:
        raise ValueError("Название профиля стилей не может быть пустым")
    now = _utcnow()
    payload = json.dumps(styles, ensure_ascii=False)
    with connect() as con:
        existing = con.execute(
            "SELECT id FROM style_profiles WHERE project_id IS ? AND name=?",
            (project_id, name),
        ).fetchone()
        if existing:
            con.execute(
                "UPDATE style_profiles SET grouping_column=?, styles_json=?, updated_at=? WHERE id=?",
                (grouping_column, payload, now, existing["id"]),
            )
            con.commit()
            return int(existing["id"])
        cur = con.execute(
            "INSERT INTO style_profiles(project_id, name, grouping_column, styles_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (project_id, name, grouping_column, payload, now, now),
        )
        con.commit()
        return int(cur.lastrowid)


def list_style_profiles(project_id: int | None = None) -> list[dict]:
    with connect() as con:
        if project_id is None:
            rows = con.execute("SELECT * FROM style_profiles ORDER BY updated_at DESC, name").fetchall()
        else:
            rows = con.execute(
                "SELECT * FROM style_profiles WHERE project_id IS NULL OR project_id=? ORDER BY updated_at DESC, name",
                (project_id,),
            ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["styles"] = json.loads(d.pop("styles_json"))
        out.append(d)
    return out


def delete_style_profile(profile_id: int) -> None:
    with connect() as con:
        con.execute("DELETE FROM style_profiles WHERE id=?", (profile_id,))
        con.commit()
