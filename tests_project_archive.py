from __future__ import annotations

import json
import tempfile
import zipfile
from pathlib import Path

import petrolab.project_archive as project_archive


def test_archive_modes_and_manifest(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        db_path = root / "petrolab.sqlite3"
        db_path.write_bytes(b"sqlite-snapshot")
        source = root / "source.xlsx"
        source.write_bytes(b"xlsx")
        assets = root / "assets"
        project_assets = assets / "project_1" / "dataset_2"
        project_assets.mkdir(parents=True)
        image = project_assets / "image.png"
        image.write_bytes(b"png")

        monkeypatch.setattr(project_archive, "DB_PATH", db_path)
        monkeypatch.setattr(project_archive, "ASSETS_DIR", assets)
        monkeypatch.setattr(
            project_archive,
            "list_projects",
            lambda: [{"id": 1, "name": "Test project", "description": "demo"}],
        )
        monkeypatch.setattr(
            project_archive,
            "list_datasets",
            lambda project_id: [{"id": 2, "source_path": str(source)}],
        )

        target = root / "full.petrolab"
        result = project_archive.create_project_archive(1, target, mode="full")
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
            assert manifest["format"] == "petrolab-project-archive"
            assert manifest["mode"] == "full"


def test_project_only_excludes_sources_and_images(monkeypatch):
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        db_path = root / "petrolab.sqlite3"
        db_path.write_bytes(b"sqlite-snapshot")
        monkeypatch.setattr(project_archive, "DB_PATH", db_path)
        monkeypatch.setattr(project_archive, "ASSETS_DIR", root / "assets")
        monkeypatch.setattr(project_archive, "list_projects", lambda: [{"id": 1, "name": "P"}])
        monkeypatch.setattr(project_archive, "list_datasets", lambda project_id: [])

        target = root / "small.petrolab"
        project_archive.create_project_archive(1, target, mode="project", image_mode="none")
        with zipfile.ZipFile(target) as archive:
            names = set(archive.namelist())
            assert names == {"database/petrolab.sqlite3", "manifest.json"}
