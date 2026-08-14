from __future__ import annotations

import gc
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import petrolab.db as db
from petrolab.derived import load_dataset_with_derived, save_point_formula_results
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
            con.execute("INSERT INTO projects(name, description, created_at) VALUES ('PG', '', '2026-08-14')")
            project_id = int(con.execute("SELECT id FROM projects").fetchone()["id"])
            con.execute(
                """
                INSERT INTO datasets(
                    project_id, name, mineral_key, source_filename, source_sheet,
                    source_sha256, csv_path, row_count, imported_at
                ) VALUES (?, 'mixed', 'mica', 'x.xlsx', 'Sheet1', 'x', 'x.csv', 1, '2026-08-14')
                """,
                (project_id,),
            )
            self.dataset_id = int(con.execute("SELECT id FROM datasets").fetchone()["id"])
            con.execute(
                """
                INSERT INTO analysis_rows(analysis_id, dataset_id, row_index, source_row, data_json, updated_at)
                VALUES ('a1', ?, 0, 2, '{"SiO2":40.0,"MgO":50.0,"FeO":10.0}', '2026-08-14')
                """,
                (self.dataset_id,),
            )
            con.commit()
        return self

    def __exit__(self, exc_type, exc, tb):
        gc.collect()
        self.stack.close()
        gc.collect()


class PointFormulaTests(unittest.TestCase):
    def test_point_formula_is_loaded_without_replacing_dataset_default(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            source = db.load_dataset_dataframe(ws.dataset_id, include_meta=True)
            result = source.copy()
            result["apfu_Mg"] = 2.0
            result["formula_valid"] = True
            saved = save_point_formula_results(
                ws.dataset_id, "olivine", "ol_4o_fe2", "4 O",
                source, result,
            )
            self.assertEqual(saved.row_count, 1)
            loaded = load_dataset_with_derived(ws.dataset_id)
            self.assertEqual(float(loaded.loc[0, "apfu_Mg"]), 2.0)
            self.assertEqual(loaded.loc[0, "Минерал"], "mica")


if __name__ == "__main__":
    unittest.main()
