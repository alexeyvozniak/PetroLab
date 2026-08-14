from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import petrolab.db as db
from petrolab.analysis_groups import set_work_group
from petrolab.generations import (
    PETROLAB_GENERATION_COLUMN,
    SOURCE_GENERATION_COLUMN,
    assign_generation,
    attach_generations,
    clear_generation,
    generation_history,
    promote_work_group,
)
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
            con.execute("""INSERT INTO datasets(id, project_id, name, mineral_key, source_filename, source_sheet, source_sha256, csv_path, row_count, imported_at)
                           VALUES (10, ?, 'D10', 'phlogopite', 'probe.xlsx', 'Sheet1', 'sha', '', 2, '2026-08-14')""", (project_id,))
            con.execute("INSERT INTO analysis_rows(analysis_id, dataset_id, row_index, source_row, data_json, updated_at) VALUES ('a1', 10, 0, 2, '{\"Generation\":\"core\"}', '2026-08-14')")
            con.execute("INSERT INTO analysis_rows(analysis_id, dataset_id, row_index, source_row, data_json, updated_at) VALUES ('a2', 10, 1, 3, '{\"Generation\":\"rim\"}', '2026-08-14')")
            con.commit()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stack.close()


class GenerationTests(unittest.TestCase):
    def test_assignment_preserves_source_generation(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)):
            assign_generation(["a1"], "N-X1", rationale="chemistry + texture")
            frame = pd.DataFrame({"_analysis_id": ["a1", "a2"], "Generation": ["core", "rim"]})
            out = attach_generations(frame)
            self.assertEqual(out.loc[0, SOURCE_GENERATION_COLUMN], "core")
            self.assertEqual(out.loc[0, PETROLAB_GENERATION_COLUMN], "N-X1")
            self.assertEqual(out.loc[1, PETROLAB_GENERATION_COLUMN], "")

    def test_work_group_can_be_promoted_without_changing_source_row(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)):
            set_work_group(["a1", "a2"], "high-Ti cores")
            self.assertEqual(promote_work_group("high-Ti cores", "N-X2"), 2)
            with db.connect() as con:
                source = con.execute("SELECT data_json FROM analysis_rows WHERE analysis_id='a1'").fetchone()["data_json"]
            self.assertIn('"Generation":"core"', source)

    def test_changes_are_historic_and_reversible(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)):
            assign_generation(["a1"], "N-X1")
            assign_generation(["a1"], "N-X2", rationale="revised")
            self.assertEqual(clear_generation(["a1"], rationale="uncertain"), 1)
            history = generation_history(["a1"])
            self.assertEqual(len(history), 3)
            self.assertEqual(history[0]["previous_generation"], "N-X2")
            self.assertEqual(history[0]["new_generation"], "")


if __name__ == "__main__":
    unittest.main()
