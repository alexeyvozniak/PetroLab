from __future__ import annotations

import gc
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import petrolab.db as db
import petrolab.sample_registry as registry
from petrolab.storage import ensure_storage


class Workspace:
    def __init__(self, root: Path):
        self.root = root
        self.stack = ExitStack()

    def __enter__(self):
        data = self.root / "data"
        for module in (db, registry):
            if hasattr(module, "DATA_DIR"):
                self.stack.enter_context(patch.object(module, "DATA_DIR", data))
        self.stack.enter_context(patch.object(db, "DATA_DIR", data))
        self.stack.enter_context(patch.object(db, "DB_PATH", data / "petrolab.sqlite3"))
        self.stack.enter_context(patch.object(db, "ASSETS_DIR", data / "assets"))
        self.stack.enter_context(patch.object(db, "BACKUPS_DIR", data / "backups"))
        ensure_storage()
        with db.connect() as con:
            con.execute("INSERT INTO projects(name, description, created_at) VALUES ('Kovdor 2026', '', '2026-08-14')")
            self.project_id = int(con.execute("SELECT id FROM projects WHERE name='Kovdor 2026'").fetchone()["id"])
            con.commit()
        return self

    def __exit__(self, exc_type, exc, tb):
        # sqlite3.Row objects can keep references to statements until GC on Windows.
        # Force collection before TemporaryDirectory attempts to remove the DB file.
        gc.collect()
        self.stack.close()
        gc.collect()


class SampleRegistryTests(unittest.TestCase):
    def test_separator_variants_are_suggestions_not_automatic_merge(self):
        self.assertEqual(registry.normalize_sample_key("PG-15"), registry.normalize_sample_key("PG_15"))
        self.assertEqual(registry.normalize_sample_key("PG-15"), registry.normalize_sample_key("pg 15"))
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            sid = registry.create_sample(ws.project_id, "PG-15")
            matches = registry.find_sample_matches(ws.project_id, "PG_15")
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0].sample_id, sid)
            self.assertEqual(matches[0].match_kind, "normalized")
            self.assertEqual(len(registry.list_samples(ws.project_id)), 1)
            del matches

    def test_confirmed_alias_resolves_to_canonical_sample(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            sid = registry.create_sample(ws.project_id, "PG-15")
            registry.add_sample_alias(sid, "ПГ_15", source="user_confirmed")
            matches = registry.find_sample_matches(ws.project_id, "ПГ_15")
            self.assertEqual(matches[0].sample_id, sid)
            self.assertIn(matches[0].match_kind, {"alias", "normalized"})
            samples = registry.list_samples(ws.project_id)
            self.assertIn("ПГ_15", samples[0]["aliases"])
            del matches, samples

    def test_empty_field_samples_are_valid_records(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            registry.create_sample(ws.project_id, "KV-01", field_lithology="карбонатит", locality="Ковдор")
            rows = registry.list_samples(ws.project_id)
            self.assertEqual(rows[0]["name"], "KV-01")
            self.assertEqual(rows[0]["field_lithology"], "карбонатит")
            self.assertEqual(rows[0]["locality"], "Ковдор")
            del rows


if __name__ == "__main__":
    unittest.main()
