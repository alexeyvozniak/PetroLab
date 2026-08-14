from __future__ import annotations

import gc
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import petrolab.db as db
from petrolab.analytical_sessions import attach_datasets, create_session
from petrolab.phase_suggestions import materialize_confirmed_phases, mineral_key_for_phase
from petrolab.repositories.image_repository import create_image_record, list_image_records
from petrolab.sample_registry import create_sample
from petrolab.storage import ensure_storage
from petrolab.workflow_screening import OUTLIER_COLUMN, attach_chemical_outlier_screen


class Workspace:
    def __init__(self, root: Path):
        self.root = root
        self.stack = ExitStack()
        self.project_id = 0
        self.other_project_id = 0
        self.session_id = 0
        self.asset_id = 0

    def __enter__(self):
        data = self.root / "data"
        self.stack.enter_context(patch.object(db, "DATA_DIR", data))
        self.stack.enter_context(patch.object(db, "DB_PATH", data / "petrolab.sqlite3"))
        self.stack.enter_context(patch.object(db, "ASSETS_DIR", data / "assets"))
        self.stack.enter_context(patch.object(db, "BACKUPS_DIR", data / "backups"))
        ensure_storage()
        with db.connect() as con:
            con.execute("INSERT INTO projects(name, description, created_at) VALUES ('Demo', '', '2026-08-14')")
            con.execute("INSERT INTO projects(name, description, created_at) VALUES ('Second', '', '2026-08-14')")
            self.project_id = int(con.execute("SELECT id FROM projects WHERE name='Demo'").fetchone()["id"])
            self.other_project_id = int(con.execute("SELECT id FROM projects WHERE name='Second'").fetchone()["id"])
            con.execute(
                """INSERT INTO datasets(id, project_id, name, mineral_key, source_filename, source_sheet,
                                         source_sha256, csv_path, row_count, imported_at, source_kind)
                   VALUES (10, ?, 'mixed probe', 'generic', 'probe.xlsx', 'Sheet1', 'sha', '', 2,
                           '2026-08-14', 'managed_copy')""",
                (self.project_id,),
            )
            con.executemany(
                """INSERT INTO project_dataset_links(project_id, dataset_id, note, added_at, purpose)
                   VALUES (?, 10, ?, '2026-08-14', 'working')""",
                [
                    (self.project_id, "working project"),
                    (self.other_project_id, "comparison project"),
                ],
            )
            con.execute(
                """INSERT INTO analysis_rows(analysis_id,dataset_id,row_index,source_row,data_json,updated_at)
                   VALUES ('a1',10,0,2,'{"SiO2":40.0,"Al2O3":15.0,"MgO":20.0,"FeO":10.0,"K2O":9.0}','2026-08-14')"""
            )
            con.execute(
                """INSERT INTO analysis_rows(analysis_id,dataset_id,row_index,source_row,data_json,updated_at)
                   VALUES ('a2',10,1,3,'{"SiO2":51.0,"CaO":20.0,"MgO":15.0,"FeO":7.0,"Al2O3":3.0}','2026-08-14')"""
            )
            con.commit()

        sample_id = create_sample(self.project_id, "PG-1")
        self.session_id = create_session(self.project_id, sample_id, technique="EPMA_WDS", session_date="2026-08-14")
        attach_datasets(self.session_id, [10])
        self.asset_id = create_image_record(
            project_id=self.project_id,
            dataset_id=10,
            analysis_ids=["a1"],
            scope_type="Точки анализа",
            scope_column="",
            scope_value="",
            kind="BSE",
            title="grain 1",
            original_filename="grain1.png",
            stored_path=str(data / "assets" / "grain1.png"),
        )
        return self

    def __exit__(self, exc_type, exc, tb):
        gc.collect()
        self.stack.close()


class GuidedWorkflowTests(unittest.TestCase):
    def test_outlier_screen_is_conservative_and_non_destructive(self):
        frame = pd.DataFrame([
            {"Suggested Mineral": "clinopyroxene", "SiO2": 51.0, "MgO": 15.0, "CaO": 21.0},
            {"Suggested Mineral": "clinopyroxene", "SiO2": 51.2, "MgO": 15.1, "CaO": 20.9},
            {"Suggested Mineral": "clinopyroxene", "SiO2": 50.8, "MgO": 14.9, "CaO": 21.1},
            {"Suggested Mineral": "clinopyroxene", "SiO2": 51.1, "MgO": 15.0, "CaO": 21.0},
            {"Suggested Mineral": "clinopyroxene", "SiO2": 50.9, "MgO": 15.2, "CaO": 20.8},
            {"Suggested Mineral": "clinopyroxene", "SiO2": 51.0, "MgO": 14.8, "CaO": 21.2},
            {"Suggested Mineral": "clinopyroxene", "SiO2": 51.3, "MgO": 15.1, "CaO": 20.9},
            {"Suggested Mineral": "clinopyroxene", "SiO2": 50.7, "MgO": 15.0, "CaO": 21.0},
            {"Suggested Mineral": "clinopyroxene", "SiO2": 41.0, "MgO": 30.0, "CaO": 10.0},
        ])
        original = frame.copy(deep=True)
        screened = attach_chemical_outlier_screen(frame, group_column="Suggested Mineral")
        pd.testing.assert_frame_equal(frame, original)
        self.assertEqual(int(screened[OUTLIER_COLUMN].sum()), 1)
        self.assertTrue(bool(screened.iloc[-1][OUTLIER_COLUMN]))

        too_small = attach_chemical_outlier_screen(frame.iloc[:7], group_column="Suggested Mineral")
        self.assertFalse(bool(too_small[OUTLIER_COLUMN].any()))

    def test_phase_labels_map_to_safe_formula_modules(self):
        self.assertEqual(mineral_key_for_phase("trioctahedral mica"), "mica")
        self.assertEqual(mineral_key_for_phase("REE-Na titanate (loparite-type)"), "perovskite")
        self.assertEqual(mineral_key_for_phase("pyrochlore-supergroup"), "generic")
        self.assertEqual(mineral_key_for_phase("моя редкая фаза"), "generic")

    def test_split_preserves_projects_session_image_links_and_mixed_remainder(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as workspace:
            created = materialize_confirmed_phases(10, {"a1": "trioctahedral mica"})
            child_id = int(created["trioctahedral mica"])
            with db.connect() as con:
                child = con.execute("SELECT name, mineral_key, row_count FROM datasets WHERE id=?", (child_id,)).fetchone()
                source = con.execute("SELECT name, row_count FROM datasets WHERE id=10").fetchone()
                projects = {
                    int(row["project_id"])
                    for row in con.execute("SELECT project_id FROM project_dataset_links WHERE dataset_id=?", (child_id,)).fetchall()
                }
                sessions = {
                    int(row["session_id"])
                    for row in con.execute("SELECT session_id FROM analytical_session_datasets WHERE dataset_id=?", (child_id,)).fetchall()
                }
                total = int(con.execute("SELECT COUNT(*) FROM analysis_rows").fetchone()[0])
            self.assertEqual(child["mineral_key"], "mica")
            self.assertIn("trioctahedral mica", child["name"])
            self.assertEqual(int(child["row_count"]), 1)
            self.assertIn("Неразобранные / mixed", source["name"])
            self.assertEqual(int(source["row_count"]), 1)
            self.assertEqual(projects, {workspace.project_id, workspace.other_project_id})
            self.assertIn(workspace.session_id, sessions)
            self.assertEqual(total, 2)

            child_images = list_image_records(dataset_id=child_id)
            self.assertEqual([int(item["id"]) for item in child_images], [workspace.asset_id])
            self.assertEqual(child_images[0]["analysis_ids"], ["a1"])


if __name__ == "__main__":
    unittest.main()
