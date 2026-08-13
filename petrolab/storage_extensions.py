from __future__ import annotations

import sqlite3


ROCK_ISOTOPE_COLUMNS = (
    "id", "rock_id", "system", "ratio_name", "analysis_label", "value", "uncertainty",
    "initial_value", "age_ma_used", "method", "laboratory", "source", "notes", "updated_at",
)


def _create_rock_isotopes_table(con: sqlite3.Connection, table_name: str = "rock_isotopes") -> None:
    con.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rock_id INTEGER NOT NULL,
            system TEXT NOT NULL DEFAULT '',
            ratio_name TEXT NOT NULL,
            analysis_label TEXT NOT NULL DEFAULT '',
            value REAL,
            uncertainty REAL,
            initial_value REAL,
            age_ma_used REAL,
            method TEXT NOT NULL DEFAULT '',
            laboratory TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            FOREIGN KEY(rock_id) REFERENCES rock_samples(id) ON DELETE CASCADE
        )
        """
    )


def _migrate_rock_isotopes(con: sqlite3.Connection) -> None:
    """Remove the legacy one-ratio-per-rock constraint without losing old isotope rows."""
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='rock_isotopes'"
    ).fetchone()
    if row is None:
        _create_rock_isotopes_table(con)
        return

    table_sql = str(row[0] or "").replace(" ", "").lower()
    existing_columns = {
        str(info[1]) for info in con.execute("PRAGMA table_info(rock_isotopes)").fetchall()
    }
    needs_rebuild = (
        "unique(rock_id,ratio_name)" in table_sql
        or "analysis_label" not in existing_columns
        or "source" not in existing_columns
    )
    if not needs_rebuild:
        return

    con.execute("DROP TABLE IF EXISTS rock_isotopes_new")
    _create_rock_isotopes_table(con, "rock_isotopes_new")

    select_expressions: list[str] = []
    for column in ROCK_ISOTOPE_COLUMNS:
        if column in existing_columns:
            select_expressions.append(column)
        elif column in {"analysis_label", "source"}:
            select_expressions.append("''")
        else:
            select_expressions.append("NULL")
    con.execute(
        f"""
        INSERT INTO rock_isotopes_new({', '.join(ROCK_ISOTOPE_COLUMNS)})
        SELECT {', '.join(select_expressions)} FROM rock_isotopes
        """
    )
    con.execute("DROP TABLE rock_isotopes")
    con.execute("ALTER TABLE rock_isotopes_new RENAME TO rock_isotopes")


def ensure_rock_tables(con: sqlite3.Connection) -> None:
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS rock_samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            massif TEXT NOT NULL DEFAULT '',
            locality TEXT NOT NULL DEFAULT '',
            lithology TEXT NOT NULL DEFAULT '',
            latitude REAL,
            longitude REAL,
            age_ma REAL,
            age_uncertainty_ma REAL,
            age_method TEXT NOT NULL DEFAULT '',
            chemistry_method TEXT NOT NULL DEFAULT '',
            isotope_method TEXT NOT NULL DEFAULT '',
            laboratory TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(project_id, name),
            FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS rock_compositions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rock_id INTEGER NOT NULL,
            analyte TEXT NOT NULL,
            value REAL,
            unit TEXT NOT NULL DEFAULT '',
            method TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(rock_id, analyte),
            FOREIGN KEY(rock_id) REFERENCES rock_samples(id) ON DELETE CASCADE
        )
        """
    )
    _migrate_rock_isotopes(con)
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS rock_mineral_links (
            rock_id INTEGER NOT NULL,
            dataset_id INTEGER NOT NULL,
            relationship TEXT NOT NULL DEFAULT 'minerals_from_rock',
            notes TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            PRIMARY KEY(rock_id, dataset_id),
            FOREIGN KEY(rock_id) REFERENCES rock_samples(id) ON DELETE CASCADE,
            FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
        )
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS rock_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rock_id INTEGER NOT NULL,
            kind TEXT NOT NULL DEFAULT 'Фото породы',
            title TEXT NOT NULL DEFAULT '',
            original_filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            added_at TEXT NOT NULL,
            FOREIGN KEY(rock_id) REFERENCES rock_samples(id) ON DELETE CASCADE
        )
        """
    )
    con.execute("CREATE INDEX IF NOT EXISTS idx_rock_project ON rock_samples(project_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rock_comp_rock ON rock_compositions(rock_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rock_iso_rock ON rock_isotopes(rock_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rock_iso_ratio ON rock_isotopes(rock_id, ratio_name)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_rock_links_dataset ON rock_mineral_links(dataset_id)")
