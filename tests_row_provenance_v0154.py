from __future__ import annotations

import gc
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import petrolab.db as db
import petrolab.row_provenance as provenance
import petrolab.sample_registry as samples
import petrolab.source_registry as sources
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
            con.execute("INSERT INTO projects(name, description, created_at) VALUES ('Import test', '', '2026-08-15')")
            self.project_id = int(con.execute("SELECT id FROM projects WHERE name='Import test'").fetchone()["id"])
            con.commit()
        return self

    def __exit__(self, exc_type, exc, tb):
        gc.collect()
        self.stack.close()
        gc.collect()


class RowProvenanceTests(unittest.TestCase):
    def test_transliteration_is_a_question_not_an_automatic_merge(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            sample_id = samples.create_sample(ws.project_id, "Kandalaksha")
            self.assertIsNone(
                provenance.canonical_sample_id(
                    ws.project_id, "Кандалакша", create_if_missing=False,
                )
            )
            candidates = provenance.sample_reconciliation_candidates(ws.project_id, ["Кандалакша"])
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].existing_id, sample_id)
            self.assertGreaterEqual(candidates[0].score, 0.99)
            resolved = provenance.canonical_sample_id(
                ws.project_id, "Кандалакша", confirmed_existing_id=sample_id,
            )
            self.assertEqual(resolved, sample_id)
            record = samples.list_samples(ws.project_id)[0]
            self.assertIn("Кандалакша", record["aliases"])

    def test_case_only_variant_is_a_question_not_an_automatic_merge(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            sample_id = samples.create_sample(ws.project_id, "19KL23")
            self.assertIsNone(
                provenance.canonical_sample_id(
                    ws.project_id, "19kl23", create_if_missing=False,
                )
            )
            candidates = provenance.sample_reconciliation_candidates(ws.project_id, ["19kl23"])
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].reason, "отличается только регистром")
            resolved = provenance.canonical_sample_id(
                ws.project_id, "19kl23", confirmed_existing_id=sample_id,
            )
            self.assertEqual(resolved, sample_id)
            record = samples.list_samples(ws.project_id)[0]
            self.assertIn("19kl23", record["aliases"])

    def test_source_transliteration_does_not_silently_reuse_study(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            study_id = sources.create_study(
                ws.project_id,
                source_type="article",
                citation="Kandalaksha compilation",
            )
            self.assertIsNone(
                provenance.canonical_study_id(
                    ws.project_id, "Кандалакша compilation", create_if_missing=False,
                )
            )
            candidates = provenance.source_reconciliation_candidates(
                ws.project_id, ["Кандалакша compilation"]
            )
            self.assertEqual(candidates[0].existing_id, study_id)
            self.assertEqual(
                provenance.canonical_study_id(
                    ws.project_id,
                    "Кандалакша compilation",
                    confirmed_existing_id=study_id,
                ),
                study_id,
            )


if __name__ == "__main__":
    unittest.main()
