from __future__ import annotations

import sqlite3

from . import db as _db
from .storage_extensions import ensure_rock_tables


def ensure_storage() -> None:
    """Create/migrate PetroLab storage and always close the bootstrap SQLite handle."""
    _db.DATA_DIR.mkdir(parents=True, exist_ok=True)
    _db.ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    _db.BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

    con = sqlite3.connect(_db.DB_PATH)
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
        existing = _db._table_columns(con, "datasets")
        for col, ddl in _db.DATASET_EXTRA_COLUMNS.items():
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

        ensure_rock_tables(con)
        con.commit()
    finally:
        con.close()
