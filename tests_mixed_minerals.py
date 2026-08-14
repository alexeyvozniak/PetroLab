from __future__ import annotations

import gc
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import petrolab.db as db
from petrolab.phase_suggestions import attach_phase_suggestions, materialize_confirmed_phases
from petrolab.storage import ensure_storage


class Workspace:
    def __init__(self, root: Path):
        self.root = root
        self.stack = ExitStack()

    def __enter__(self):
        data = self.root / "data"
        self.stack.enter_context(patch.object(db, "DATA_DIR", data))
        self.stack.enter_context(patch.object(db, "DB_PATH", data / "petrolab.sqlite3"))
        self.stack.enter_context(patch.object(db, "ASSETS_DIR", data / "assets"))
        self.stack.enter_context(patch.object(db, "BACKUPS_DIR", data / "backups"))
        ensure_storage()
        with db.connect() as con:
            con.execute("INSERT INTO projects(name, description, created_at) VALUES ('Demo', '', '2026-08-14')")
            project_id = int(con.execute("SELECT id FROM projects WHERE name='Demo'").fetchone()["id"])
            con.execute("""INSERT INTO datasets(id, project_id, name, mineral_key, source_filename, source_sheet, source_sha256, csv_path, row_count, imported_at, source_kind)
                           VALUES (10, ?, 'mixed probe', 'generic', 'probe.xlsx', 'Sheet1', 'sha', '', 3, '2026-08-14', 'managed_copy')""", (project_id,))
            rows = [
                ("a1", 0, 2, '{"SiO2":40.0,"Al2O3":15.0,"MgO":20.0,"FeO":10.0,"K2O":9.0}'),
                ("a2", 1, 3, '{"P2O5":42.0,"CaO":55.0,"F":3.0}'),
                ("a3", 2, 4, '{"SiO2":51.0,"CaO":20.0,"MgO":15.0,"FeO":7.0,"Al2O3":3.0}'),
            ]
            for aid, index, source_row, payload in rows:
                con.execute("INSERT INTO analysis_rows(analysis_id,dataset_id,row_index,source_row,data_json,updated_at) VALUES (?,10,?,?,?,'2026-08-14')", (aid, index, source_row, payload))
            con.commit()
        return self

    def __exit__(self, exc_type, exc, tb):
        gc.collect()
        self.stack.close()


class MixedMineralTests(unittest.TestCase):
    def test_diagnostic_phases_are_suggested_and_overlap_can_remain_unresolved(self):
        frame = pd.DataFrame([
            {"SiO2": 40.0, "Al2O3": 15.0, "MgO": 20.0, "FeO": 10.0, "K2O": 9.0},
            {"P2O5": 42.0, "CaO": 55.0, "F": 3.0},
            {"TiO2": 55.0, "CaO": 40.0, "SiO2": 1.0},
        ])
        out = attach_phase_suggestions(frame)
        self.assertEqual(out.loc[0, "Suggested Mineral"], "trioctahedral mica")
        self.assertEqual(out.loc[1, "Suggested Mineral"], "apatite")
        self.assertEqual(out.loc[2, "Suggested Mineral"], "perovskite")
        self.assertTrue((out["Mineral suggestion confidence"] == "high").all())
        self.assertTrue(out["Mineral suggestion ruleset"].astype(str).str.len().gt(0).all())

    def test_materialization_moves_rows_without_duplicate_analysis_ids(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)):
            created = materialize_confirmed_phases(10, {"a1": "trioctahedral mica", "a2": "apatite"})
            self.assertEqual(set(created), {"trioctahedral mica", "apatite"})
            with db.connect() as con:
                rows = con.execute("SELECT analysis_id,dataset_id FROM analysis_rows ORDER BY analysis_id").fetchall()
                total = con.execute("SELECT COUNT(*) FROM analysis_rows").fetchone()[0]
                source_count = con.execute("SELECT row_count FROM datasets WHERE id=10").fetchone()[0]
            self.assertEqual(total, 3)
            self.assertEqual(len({row["analysis_id"] for row in rows}), 3)
            self.assertEqual(source_count, 1)
            self.assertEqual([row["analysis_id"] for row in rows if row["dataset_id"] == 10], ["a3"])


if __name__ == "__main__":
    unittest.main()
