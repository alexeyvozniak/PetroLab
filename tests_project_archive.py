from __future__ import annotations

import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

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


def _patch_workspace(monkeypatch, root: Path):
    db_path = root / "petrolab.sqlite3"
    _make_db(db_path)
    assets = root / "assets"
    backups = root / "backups"
    data = root / "data"
    project_assets = assets / "project_1" / "dataset_2"
    project_assets.mkdir(parents=True)
    image = project_assets / "image.png"
    Image.new("RGB", (50, 40), "white").save(image)
    source = root / "source.xlsx"
    source.write_bytes(b"xlsx")

    monkeypatch.setattr(project_archive, "DB_PATH", db_path)
    monkeypatch.setattr(project_archive, "ASSETS_DIR", assets)
    monkeypatch.setattr(project_archive, "BACKUPS_DIR", backups)
    monkeypatch.setattr(project_archive, "DATA_DIR", data)
    monkeypatch.setattr(project_archive, "ensure_storage", lambda: None)
    monkeypatch.setattr(
        project_archive,
        "list_projects",
        lambda: [{"id": 1, "name": "Test project", "description": "demo"}],
    )
    monkeypatch.setattr(
        project_archive,
        "list_datasets",
        lambda project_id: [{"id": 2, "source_path": str(source), "source_filename": "source.xlsx"}],
    )
    return db_path, source, image


def test_archive_is_project_scoped(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _patch_workspace(monkeypatch, root)
        target = root / "full.petrolab"
        result = project_archive.create_project_archive(1, target, mode="full", image_mode="originals")
        assert result.dataset_count == 1
        assert result.source_count == 1
        assert result.image_count == 1

        with zipfile.ZipFile(target) as archive:
            names = set(archive.namelist())
            assert "database/petrolab.sqlite3" in names
            assert "manifest.json" in names
            assert any(name.startswith("sources/") for name in names)
            assert "images/dataset_2/image.png" in names
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["format_version"] == 2
            snapshot = root / "snapshot.sqlite3"
            snapshot.write_bytes(archive.read("database/petrolab.sqlite3"))
        con = sqlite3.connect(snapshot)
        try:
            assert con.execute("SELECT name FROM projects").fetchall() == [("Test project",)]
            assert con.execute("SELECT id FROM datasets").fetchall() == [(2,)]
            assert con.execute("SELECT analysis_id FROM analysis_rows").fetchall() == [("a1",)]
            assert con.execute("SELECT id FROM image_assets").fetchall() == [(3,)]
            assert con.execute("SELECT asset_id FROM image_analysis_links").fetchall() == [(3,)]
        finally:
            con.close()


def test_optimized_images_are_derivatives(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _patch_workspace(monkeypatch, root)
        target = root / "optimized.petrolab"
        project_archive.create_project_archive(1, target, mode="full", image_mode="optimized")
        with zipfile.ZipFile(target) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["optimized_images_are_derivatives"] is True
            assert any(name.startswith("images/") and name.endswith(".jpg") for name in archive.namelist())


def test_project_only_excludes_sources_and_images(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _patch_workspace(monkeypatch, root)
        target = root / "small.petrolab"
        project_archive.create_project_archive(1, target, mode="project", image_mode="none")
        with zipfile.ZipFile(target) as archive:
            names = set(archive.namelist())
            assert names == {"database/petrolab.sqlite3", "manifest.json"}


def test_restore_refuses_nonempty_workspace_without_confirmation(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        _patch_workspace(monkeypatch, root)
        archive_path = root / "portable.petrolab"
        project_archive.create_project_archive(1, archive_path, mode="project", image_mode="none")
        try:
            project_archive.restore_project_archive(archive_path, allow_replace_workspace=False)
        except ValueError as exc:
            assert "уже есть проекты" in str(exc)
        else:
            raise AssertionError("Restore must refuse a non-empty workspace without explicit replacement")
