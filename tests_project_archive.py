from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
import zipfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import petrolab.project_archive as project_archive


def _make_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE projects(id INTEGER PRIMARY KEY, name TEXT, description TEXT);
        CREATE TABLE datasets(id INTEGER PRIMARY KEY, project_id INTEGER, source_filename TEXT, source_path TEXT);
        CREATE TABLE analysis_rows(analysis_id TEXT PRIMARY KEY, dataset_id INTEGER);
        CREATE TABLE image_assets(id INTEGER PRIMARY KEY, project_id INTEGER, dataset_id INTEGER, analysis_id TEXT, stored_path TEXT);
        CREATE TABLE image_analysis_links(asset_id INTEGER, analysis_id TEXT);
        CREATE TABLE plot_recipes(id INTEGER PRIMARY KEY, project_id INTEGER, name TEXT);
        """
    )
    con.execute("INSERT INTO projects VALUES (1, 'Test project', 'demo')")
    con.execute("INSERT INTO projects VALUES (9, 'Other project', 'must not travel')")
    con.execute("INSERT INTO datasets VALUES (2, 1, 'source.xlsx', '/old/source.xlsx')")
    con.execute("INSERT INTO datasets VALUES (10, 9, 'other.xlsx', '/old/other.xlsx')")
    con.execute("INSERT INTO analysis_rows VALUES ('a1', 2)")
    con.execute("INSERT INTO analysis_rows VALUES ('other-a', 10)")
    con.execute("INSERT INTO image_assets VALUES (3, 1, 2, 'a1', '/old/assets/image.png')")
    con.execute("INSERT INTO image_assets VALUES (11, 9, 10, 'other-a', '/old/assets/other.png')")
    con.execute("INSERT INTO image_analysis_links VALUES (3, 'a1')")
    con.execute("INSERT INTO image_analysis_links VALUES (11, 'other-a')")
    con.commit()
    con.close()


class PatchedWorkspace:
    def __init__(self, root: Path):
        self.root = root
        self.stack = ExitStack()
        self.db_path = root / "petrolab.sqlite3"
        _make_db(self.db_path)
        self.assets = root / "assets"
        self.backups = root / "backups"
        self.data = root / "data"
        project_assets = self.assets / "project_1" / "dataset_2"
        project_assets.mkdir(parents=True)
        self.image = project_assets / "image.png"
        Image.new("RGB", (50, 40), "white").save(self.image)
        self.source = root / "source.xlsx"
        self.source.write_bytes(b"xlsx")

    def __enter__(self):
        self.stack.enter_context(patch.object(project_archive, "DB_PATH", self.db_path))
        self.stack.enter_context(patch.object(project_archive, "ASSETS_DIR", self.assets))
        self.stack.enter_context(patch.object(project_archive, "BACKUPS_DIR", self.backups))
        self.stack.enter_context(patch.object(project_archive, "DATA_DIR", self.data))
        self.stack.enter_context(patch.object(project_archive, "ensure_storage", lambda: None))
        self.stack.enter_context(patch.object(
            project_archive,
            "list_projects",
            lambda: [{"id": 1, "name": "Test project", "description": "demo"}],
        ))
        self.stack.enter_context(patch.object(
            project_archive,
            "list_datasets",
            lambda project_id: [{"id": 2, "source_path": str(self.source), "source_filename": "source.xlsx"}],
        ))
        return self

    def __exit__(self, exc_type, exc, tb):
        self.stack.close()


class ProjectArchiveTests(unittest.TestCase):
    def test_archive_is_project_scoped(self):
        with tempfile.TemporaryDirectory() as temp_dir, PatchedWorkspace(Path(temp_dir)) as ws:
            target = ws.root / "full.petrolab"
            result = project_archive.create_project_archive(1, target, mode="full", image_mode="originals")
            self.assertEqual(result.dataset_count, 1)
            self.assertEqual(result.source_count, 1)
            self.assertEqual(result.image_count, 1)
            with zipfile.ZipFile(target) as archive:
                names = set(archive.namelist())
                self.assertIn("database/petrolab.sqlite3", names)
                self.assertIn("manifest.json", names)
                self.assertTrue(any(name.startswith("sources/") for name in names))
                self.assertIn("images/dataset_2/image.png", names)
                manifest = json.loads(archive.read("manifest.json"))
                self.assertEqual(manifest["format_version"], 2)
                snapshot = ws.root / "snapshot.sqlite3"
                snapshot.write_bytes(archive.read("database/petrolab.sqlite3"))
            con = sqlite3.connect(snapshot)
            try:
                self.assertEqual(con.execute("SELECT name FROM projects").fetchall(), [("Test project",)])
                self.assertEqual(con.execute("SELECT id FROM datasets").fetchall(), [(2,)])
                self.assertEqual(con.execute("SELECT analysis_id FROM analysis_rows").fetchall(), [("a1",)])
                self.assertEqual(con.execute("SELECT id FROM image_assets").fetchall(), [(3,)])
                self.assertEqual(con.execute("SELECT asset_id FROM image_analysis_links").fetchall(), [(3,)])
            finally:
                con.close()

    def test_optimized_images_are_derivatives(self):
        with tempfile.TemporaryDirectory() as temp_dir, PatchedWorkspace(Path(temp_dir)) as ws:
            target = ws.root / "optimized.petrolab"
            project_archive.create_project_archive(1, target, mode="full", image_mode="optimized")
            with zipfile.ZipFile(target) as archive:
                manifest = json.loads(archive.read("manifest.json"))
                self.assertTrue(manifest["optimized_images_are_derivatives"])
                self.assertTrue(any(name.startswith("images/") and name.endswith(".jpg") for name in archive.namelist()))

    def test_project_only_excludes_sources_and_images(self):
        with tempfile.TemporaryDirectory() as temp_dir, PatchedWorkspace(Path(temp_dir)) as ws:
            target = ws.root / "small.petrolab"
            project_archive.create_project_archive(1, target, mode="project", image_mode="none")
            with zipfile.ZipFile(target) as archive:
                self.assertEqual(set(archive.namelist()), {"database/petrolab.sqlite3", "manifest.json"})

    def test_restore_refuses_nonempty_workspace_without_confirmation(self):
        with tempfile.TemporaryDirectory() as temp_dir, PatchedWorkspace(Path(temp_dir)) as ws:
            archive_path = ws.root / "portable.petrolab"
            project_archive.create_project_archive(1, archive_path, mode="project", image_mode="none")
            with self.assertRaisesRegex(ValueError, "уже есть проекты"):
                project_archive.restore_project_archive(archive_path, allow_replace_workspace=False)


if __name__ == "__main__":
    unittest.main()
