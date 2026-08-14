from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import petrolab.db as db
from petrolab.analytical_sessions import (
    attach_datasets,
    create_session,
    get_or_create_sample,
    list_sessions,
    sample_history,
    set_annotations,
)


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
        db.ensure_storage()
        with db.connect() as con:
            con.execute("INSERT INTO projects(name, description, created_at) VALUES ('Demo', '', '2026-08-14')")
            project_id = int(con.execute("SELECT id FROM projects WHERE name='Demo'").fetchone()["id"])
            for dataset_id, mineral in [(10, "phlogopite"), (11, "clinopyroxene")]:
                con.execute(
                    """
                    INSERT INTO datasets(
                        id, project_id, name, mineral_key, source_filename, source_sheet,
                        source_sha256, csv_path, row_count, imported_at
                    ) VALUES (?, ?, ?, ?, 'probe.xlsx', 'Sheet1', 'sha', '', 1, '2026-08-14')
                    """,
                    (dataset_id, project_id, f"D{dataset_id}", mineral),
                )
                con.execute(
                    "INSERT INTO analysis_rows(analysis_id, dataset_id, row_index, source_row, data_json, updated_at) VALUES (?, ?, 0, 2, '{}', '2026-08-14')",
                    (f"a{dataset_id}", dataset_id),
                )
            con.commit()
        self.project_id = project_id
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stack.close()


class AnalyticalSessionTests(unittest.TestCase):
    def test_same_sample_gets_multiple_sessions_without_duplicate_sample(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            sample_id, created = get_or_create_sample(ws.project_id, "PG-15")
            self.assertTrue(created)
            repeated_id, repeated_created = get_or_create_sample(ws.project_id, "pg-15")
            self.assertEqual(repeated_id, sample_id)
            self.assertFalse(repeated_created)
            first = create_session(ws.project_id, sample_id, session_date="2026-06-03", technique="EPMA_WDS")
            second = create_session(ws.project_id, sample_id, session_date="2026-08-14", technique="LA_ICP_MS")
            self.assertNotEqual(first, second)
            sessions = list_sessions(ws.project_id, sample_id)
            self.assertEqual(len(sessions), 2)
            self.assertEqual({row["technique"] for row in sessions}, {"EPMA_WDS", "LA_ICP_MS"})

    def test_multiple_mineral_datasets_attach_to_one_session(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            sample_id, _ = get_or_create_sample(ws.project_id, "PG-15")
            session_id = create_session(ws.project_id, sample_id, session_date="2026-08-14", technique="EPMA_WDS")
            self.assertEqual(attach_datasets(session_id, [10, 11]), 2)
            history = sample_history(ws.project_id, sample_id)
            self.assertEqual(history["sessions"][0]["dataset_count"], 2)
            self.assertEqual(history["sessions"][0]["analysis_count"], 2)
            with db.connect() as con:
                rows = con.execute("SELECT DISTINCT sample_id, session_id FROM datasets ORDER BY id").fetchall()
            self.assertEqual([(row["sample_id"], row["session_id"]) for row in rows], [(sample_id, session_id), (sample_id, session_id)])

    def test_morphology_annotations_do_not_replace_generation_or_source_data(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)):
            changed = set_annotations(["a10"], {"zone": "core", "grain_size": "large"})
            self.assertEqual(changed, 1)
            with db.connect() as con:
                data_json = con.execute("SELECT data_json FROM analysis_rows WHERE analysis_id='a10'").fetchone()["data_json"]
                annotations = con.execute("SELECT key, value FROM analysis_annotations WHERE analysis_id='a10' ORDER BY key").fetchall()
            self.assertEqual(data_json, "{}")
            self.assertEqual([(row["key"], row["value"]) for row in annotations], [("grain_size", "large"), ("zone", "core")])


if __name__ == "__main__":
    unittest.main()
