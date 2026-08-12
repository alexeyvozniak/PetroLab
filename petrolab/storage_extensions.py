from __future__ import annotations

import sqlite3


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
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS rock_isotopes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rock_id INTEGER NOT NULL,
            system TEXT NOT NULL DEFAULT '',
            ratio_name TEXT NOT NULL,
            value REAL,
            uncertainty REAL,
            initial_value REAL,
            age_ma_used REAL,
            method TEXT NOT NULL DEFAULT '',
            laboratory TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(rock_id, ratio_name),
            FOREIGN KEY(rock_id) REFERENCES rock_samples(id) ON DELETE CASCADE
        )
        """
    )
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
    con.execute("CREATE INDEX IF NOT EXISTS idx_rock_links_dataset ON rock_mineral_links(dataset_id)")
