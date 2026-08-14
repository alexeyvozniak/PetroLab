from __future__ import annotations

import gc
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import petrolab.db as db
from petrolab.analytical_sessions import attach_datasets, create_session, list_sessions, sample_history, set_annotations
from petrolab.sample_registry import create_sample, find_sample_matches
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
            self.project_id = int(con.execute("SELECT id FROM projects WHERE name='Demo'").fetchone()["id"])
            con.execute("INSERT INTO projects(name, description, created_at) VALUES ('Other', '', '2026-08-14')")
            self.other_project_id = int(con.execute("SELECT id FROM projects WHERE name='Other'").fetchone()["id"])
            for dataset_id, project_id, mineral in [(10, self.project_id, "phlogopite"), (11, self.project_id, "clinopyroxene"), (12, self.other_project_id, "phlogopite")]:
                con.execute(
                    """INSERT INTO datasets(id, project_id, name, mineral_key, source_filename, source_sheet, source_sha256, csv_path, row_count, imported_at)
                       VALUES (?, ?, ?, ?, 'probe.xlsx', 'Sheet1', 'sha', '', 1, '2026-08-14')""",
                    (dataset_id, project_id, f"D{dataset_id}", mineral),
                )
                con.execute(
                    "INSERT INTO analysis_rows(analysis_id, dataset_id, row_index, source_row, data_json, updated_at) VALUES (?, ?, 0, 2, '{}', '2026-08-14')",
                    (f"a{dataset_id}", dataset_id),
                )
                con.execute(
                    "INSERT INTO project_dataset_links(project_id, dataset_id, note, added_at, purpose) VALUES (?, ?, '', '2026-08-14', 'working')",
                    (project_id, dataset_id),
                )
            con.commit()
        return self

    def __exit__(self, exc_type, exc, tb):
        # Windows can keep sqlite3.Row/statement references alive until collection.
        # Match the proven Sample Registry test cleanup before deleting the temp DB.
        gc.collect()
        self.stack.close()


class AnalyticalSessionTests(unittest.TestCase):
    def test_sessions_reuse_canonical_sample_and_do_not_create_duplicate_registry(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            sample_id = create_sample(ws.project_id, "PG-15")
            matches = find_sample_matches(ws.project_id, "PG_15")
            self.assertEqual([match.sample_id for match in matches], [sample_id])
            first = create_session(ws.project_id, sample_id, session_date="2026-06-03", technique="EPMA_WDS")
            second = create_session(ws.project_id, sample_id, session_date="2026-08-14", technique="LA_ICP_MS")
            self.assertNotEqual(first, second)
            self.assertEqual(len(list_sessions(ws.project_id, sample_id)), 2)
            with db.connect() as con:
                count = con.execute("SELECT COUNT(*) FROM samples WHERE project_id=?", (ws.project_id,)).fetchone()[0]
            self.assertEqual(count, 1)

    def test_multiple_minerals_attach_to_one_session(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            sample_id = create_sample(ws.project_id, "PG-15")
            session_id = create_session(ws.project_id, sample_id, session_date="2026-08-14", technique="EPMA_WDS")
            self.assertEqual(attach_datasets(session_id, [10, 11]), 2)
            history = sample_history(ws.project_id, sample_id)
            self.assertEqual(history["sessions"][0]["dataset_count"], 2)
            self.assertEqual(history["sessions"][0]["analysis_count"], 2)

    def test_cross_project_and_cross_sample_reattachment_are_blocked(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            first_sample = create_sample(ws.project_id, "PG-15")
            second_sample = create_sample(ws.project_id, "PG-16")
            first_session = create_session(ws.project_id, first_sample, technique="EPMA_WDS")
            second_session = create_session(ws.project_id, second_sample, technique="EPMA_WDS")
            attach_datasets(first_session, [10])
            with self.assertRaises(ValueError):
                attach_datasets(second_session, [10])
            with self.assertRaises(ValueError):
                attach_datasets(first_session, [12])

    def test_morphology_does_not_modify_source_data(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)):
            self.assertEqual(set_annotations(["a10"], {"zone": "core", "grain_size": "large"}), 1)
            with db.connect() as con:
                data_json = con.execute("SELECT data_json FROM analysis_rows WHERE analysis_id='a10'").fetchone()["data_json"]
                annotations = con.execute("SELECT key, value FROM analysis_annotations WHERE analysis_id='a10' ORDER BY key").fetchall()
            self.assertEqual(data_json, "{}")
            self.assertEqual([(row["key"], row["value"]) for row in annotations], [("grain_size", "large"), ("zone", "core")])


if __name__ == "__main__":
    unittest.main()
