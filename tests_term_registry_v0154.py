from __future__ import annotations

import gc
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import petrolab.db as db
from petrolab.storage import ensure_storage
from petrolab.term_registry import find_exact_term, list_terms, persist_staged_terms, register_term


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
            con.execute("INSERT INTO projects(name, description, created_at) VALUES ('Terms', '', '2026-08-15')")
            self.project_id = int(con.execute("SELECT id FROM projects WHERE name='Terms'").fetchone()["id"])
            con.commit()
        return self

    def __exit__(self, exc_type, exc, tb):
        gc.collect()
        self.stack.close()
        gc.collect()


class TermRegistryTests(unittest.TestCase):
    def test_confirmed_russian_alias_is_remembered_for_canonical_lithology(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            self.assertIsNone(find_exact_term(ws.project_id, "Lithology", "карбонатит"))
            term_id = register_term(
                ws.project_id,
                "Lithology",
                "carbonatite",
                aliases=["карбонатит"],
            )
            found = find_exact_term(ws.project_id, "Lithology", "карбонатит")
            self.assertIsNotNone(found)
            self.assertEqual(int(found["id"]), term_id)
            self.assertEqual(found["canonical_value"], "carbonatite")
            self.assertIn("карбонатит", found["aliases"])

    def test_staged_term_persistence_keeps_canonical_value_and_confirmed_alias(self):
        with tempfile.TemporaryDirectory() as temp_dir, Workspace(Path(temp_dir)) as ws:
            frame = pd.DataFrame({
                "Lithology": ["carbonatite", "carbonatite"],
                "Mineral": ["Phlogopite", "Phlogopite"],
            })
            count = persist_staged_terms(
                ws.project_id,
                frame,
                {
                    "Lithology": {"карбонатит": "carbonatite"},
                    "Mineral": {"флогопит": "Phlogopite"},
                },
            )
            self.assertEqual(count, 2)
            lithology = list_terms(ws.project_id, "Lithology")[0]
            mineral = list_terms(ws.project_id, "Mineral")[0]
            self.assertEqual(lithology["canonical_value"], "carbonatite")
            self.assertIn("карбонатит", lithology["aliases"])
            self.assertEqual(mineral["canonical_value"], "Phlogopite")
            self.assertIn("флогопит", mineral["aliases"])


if __name__ == "__main__":
    unittest.main()
