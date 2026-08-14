from __future__ import annotations

import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import petrolab.db as db
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
        self.project_id = db.create_project("Kovdor 2026")
        self.other_project_id = db.create_project("Literature")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stack.close()

    def add_dataset(self, project_id: int, name: str) -> int:
        return db.add_dataset(
            project_id=project_id,
            name=name,
            mineral_key="phlogopite",
            source_filename=f"{name}.xlsx",
            source_sheet="Sheet1",
            source_sha256="test-sha",
            csv_path=str(self.root / f"{name}.csv"),
            row_count=0,
            source_kind="managed_copy",
        )


class SourceRegistryTests(unittest.TestCase):
    def test_study_scoped_semantic_mappings_do_not_leak(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir, Workspace(Path(temp_dir)) as ws:
            first = sources.create_study(ws.project_id, source_type="article", citation="Author A, 2020")
            second = sources.create_study(ws.project_id, source_type="article", citation="Author B, 2021")
            sources.upsert_semantic_mapping(
                first, domain="generation", source_label="Phl-I",
                normalized_value="core", user_interpretation="primitive core",
            )
            first_rows = sources.list_semantic_mappings(first)
            second_rows = sources.list_semantic_mappings(second)
            self.assertEqual(len(first_rows), 1)
            self.assertEqual(first_rows[0]["source_label"], "Phl-I")
            self.assertEqual(second_rows, [])

    def test_cross_project_dataset_source_link_is_rejected(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir, Workspace(Path(temp_dir)) as ws:
            dataset_id = ws.add_dataset(ws.project_id, "Own data")
            foreign_study = sources.create_study(ws.other_project_id, source_type="article", citation="Foreign")
            with self.assertRaises(ValueError):
                sources.link_dataset_to_study(dataset_id, foreign_study)

    def test_data_health_reports_unlinked_dataset_and_incomplete_source(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir, Workspace(Path(temp_dir)) as ws:
            ws.add_dataset(ws.project_id, "Unlinked")
            sources.create_study(ws.project_id, source_type="other")
            health = sources.database_health(ws.project_id)
            kinds = {issue.kind for issue in health["issues"]}
            self.assertIn("unlinked_source", kinds)
            self.assertIn("study_metadata", kinds)
            self.assertLess(health["score"], 100)

    def test_linked_dataset_is_not_reported_as_unlinked(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as temp_dir, Workspace(Path(temp_dir)) as ws:
            dataset_id = ws.add_dataset(ws.project_id, "Literature mica")
            study_id = sources.create_study(ws.project_id, source_type="article", citation="Author et al., 2024")
            sources.link_dataset_to_study(dataset_id, study_id, source_table="Table S2")
            health = sources.database_health(ws.project_id)
            self.assertEqual(health["unlinked_datasets"], 0)


if __name__ == "__main__":
    unittest.main()
