from __future__ import annotations

import gc
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import petrolab.db as db
import petrolab.mineral_assignments as assignments
import petrolab.sample_locations as locations
from petrolab.measurement_registry import create_entity
import petrolab.sample_registry as registry
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
            self.project_id = int(con.execute("SELECT id FROM projects WHERE name='PG'").fetchone()["id"])
            con.execute(
                """
                INSERT INTO datasets(
                    project_id, name, mineral_key, source_filename, source_sheet,
                    source_sha256, csv_path, row_count, imported_at
                ) VALUES (?, 'Mica', 'mica', 'source.xlsx', 'Sheet1', 'x', 'x.csv', 1, '2026-08-14')
                """,
                (self.project_id,),
            )
            self.dataset_id = int(con.execute("SELECT id FROM datasets").fetchone()["id"])
            con.execute(
                """
                INSERT INTO analysis_rows(analysis_id, dataset_id, row_index, source_row, data_json, updated_at)
                VALUES ('a1', ?, 0, 2, '{"Sample":"PG-01","Point":"1"}', '2026-08-14')
                """,
                (self.dataset_id,),
            )
            con.commit()
        return self

    def __exit__(self, exc_type, exc, tb):
        gc.collect()
        self.stack.close()
        gc.collect()


class AssignmentAndLocationTests(unittest.TestCase):
    def test_reassignment_is_reversible_and_has_history(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            changed = assignments.assign_mineral("a1", "olivine", reason="выброс на графике")
            self.assertTrue(changed.changed)
            frame = assignments.attach_mineral_assignments(
                pd.DataFrame([{"_analysis_id": "a1", "Минерал": "mica"}])
            )
            self.assertEqual(frame.loc[0, "Минерал"], "olivine")
            self.assertTrue(frame.loc[0, "Минерал назначен вручную"])
            restored = assignments.assign_mineral("a1", None, reason="вернуть набор")
            self.assertTrue(restored.changed)
            frame = assignments.attach_mineral_assignments(
                pd.DataFrame([{"_analysis_id": "a1", "Минерал": "mica"}])
            )
            self.assertEqual(frame.loc[0, "Минерал"], "mica")
            self.assertFalse(frame.loc[0, "Минерал назначен вручную"])
            self.assertEqual(len(assignments.assignment_history("a1")), 2)

    def test_location_history_keeps_previous_places(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            sample_id = registry.create_sample(ws.project_id, "PG-01")
            locations.record_sample_location(sample_id, "шкаф A-3", note="после шлифовки")
            locations.record_sample_location(sample_id, "у Петра", note="на микрозонд")
            current = locations.current_sample_location(sample_id)
            self.assertIsNotNone(current)
            self.assertEqual(current.location, "у Петра")
            history = locations.sample_location_history(sample_id)
            self.assertEqual([item["location"] for item in history], ["у Петра", "шкаф A-3"])

    def test_thin_section_has_its_own_location_history(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            sample_id = registry.create_sample(ws.project_id, "PG-02")
            thin_section_id = create_entity(
                ws.project_id, kind="thin_section", name="PG-02-1", sample_id=sample_id
            )
            locations.record_entity_location(thin_section_id, "лаборатория")
            locations.record_entity_location(thin_section_id, "у оператора зонда")
            current = locations.current_entity_location(thin_section_id)
            self.assertIsNotNone(current)
            self.assertEqual(current.location, "у оператора зонда")
            self.assertEqual(len(locations.entity_location_history(thin_section_id)), 2)


if __name__ == "__main__":
    unittest.main()
