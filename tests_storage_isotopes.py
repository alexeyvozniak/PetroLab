from __future__ import annotations

import gc
import os
import sqlite3
import tempfile
from pathlib import Path

import pandas as pd


def _build_legacy_isotope_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "CREATE TABLE projects(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)"
        )
        con.execute("INSERT INTO projects(name, description, created_at) VALUES ('Legacy', '', '2026-01-01T00:00:00+00:00')")
        con.execute(
            """
            CREATE TABLE rock_samples(
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
                UNIQUE(project_id, name)
            )
            """
        )
        con.execute(
            "INSERT INTO rock_samples(project_id, name, created_at, updated_at) VALUES (1, 'LegacyRock', '2026-01-01', '2026-01-01')"
        )
        con.execute(
            """
            CREATE TABLE rock_isotopes(
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
                UNIQUE(rock_id, ratio_name)
            )
            """
        )
        con.execute(
            """
            INSERT INTO rock_isotopes(
                rock_id, system, ratio_name, value, uncertainty, method, laboratory, notes, updated_at
            ) VALUES (1, 'Sr', '87Sr/86Sr', 0.7031, 0.00002, 'TIMS', 'Legacy lab', 'preserve me', '2026-01-01')
            """
        )
        con.commit()
    finally:
        con.close()


def main() -> None:
    app_text = Path("app.py").read_text(encoding="utf-8")
    init_text = Path("petrolab/__init__.py").read_text(encoding="utf-8")
    assert "from petrolab.storage import ensure_storage" in app_text
    assert "from petrolab.db import ensure_storage" not in app_text
    assert "_db.ensure_storage" not in init_text

    with tempfile.TemporaryDirectory(prefix="petrolab_storage_iso_") as tmp:
        root = Path(tmp)
        os.environ["PETROLAB_DATA_DIR"] = str(root / "data")

        db_path = root / "data" / "petrolab.sqlite3"
        _build_legacy_isotope_database(db_path)

        import petrolab
        from petrolab import db
        from petrolab.repositories.rock_repository import get_isotopes, isotope_wide, replace_isotopes
        from petrolab.storage import ensure_storage

        assert not hasattr(petrolab, "_db"), "Package import must not monkey-patch petrolab.db"
        ensure_storage()

        con = sqlite3.connect(db.DB_PATH)
        try:
            table_sql = con.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='rock_isotopes'"
            ).fetchone()[0]
            columns = {row[1] for row in con.execute("PRAGMA table_info(rock_isotopes)").fetchall()}
            legacy = con.execute(
                "SELECT ratio_name, value, notes, analysis_label, source FROM rock_isotopes WHERE rock_id=1"
            ).fetchone()
        finally:
            con.close()

        assert "UNIQUE(rock_id, ratio_name)" not in str(table_sql)
        assert {"analysis_label", "source"}.issubset(columns)
        assert legacy[:3] == ("87Sr/86Sr", 0.7031, "preserve me")
        assert legacy[3:] == ("", "")

        repeated = pd.DataFrame(
            [
                {
                    "system": "Sr", "ratio_name": "87Sr/86Sr", "analysis_label": "aliquot A",
                    "value": 0.70310, "uncertainty": 0.00002, "initial_value": 0.70290,
                    "age_ma_used": 380.0, "method": "TIMS", "laboratory": "Lab 1",
                    "source": "run_A.xlsx", "notes": "first determination",
                },
                {
                    "system": "Sr", "ratio_name": "87Sr/86Sr", "analysis_label": "aliquot B",
                    "value": 0.70318, "uncertainty": 0.00003, "initial_value": 0.70298,
                    "age_ma_used": 380.0, "method": "TIMS", "laboratory": "Lab 1",
                    "source": "run_B.xlsx", "notes": "repeat determination",
                },
            ]
        )
        replace_isotopes(1, repeated)
        stored = get_isotopes(1)
        assert len(stored) == 2
        assert stored["ratio_name"].tolist() == ["87Sr/86Sr", "87Sr/86Sr"]
        assert set(stored["analysis_label"]) == {"aliquot A", "aliquot B"}
        assert set(stored["source"]) == {"run_A.xlsx", "run_B.xlsx"}

        wide = isotope_wide(1)
        assert "87Sr/86Sr [aliquot A]" in wide.columns
        assert "87Sr/86Sr [aliquot B]" in wide.columns
        assert float(wide.loc[0, "87Sr/86Sr [aliquot A]"]) == 0.70310
        assert float(wide.loc[0, "87Sr/86Sr [aliquot B]"]) == 0.70318

        # Windows may keep sqlite cursor/row objects alive until cyclic GC even though every
        # explicit connection above is closed. Clear local result holders and collect before
        # TemporaryDirectory removes the database file; assertions are already complete.
        del wide, stored, repeated, legacy, columns, table_sql, con
        gc.collect()

    print("storage/bootstrap/repeated-isotope tests: OK")


if __name__ == "__main__":
    main()
