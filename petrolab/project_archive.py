from __future__ import annotations

import io
import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from PIL import Image

from petrolab.db import ASSETS_DIR, BACKUPS_DIR, DATA_DIR, DB_PATH, ensure_storage, list_datasets, list_projects

ArchiveMode = Literal["project", "project_sources", "full"]
ImageMode = Literal["none", "optimized", "originals"]


@dataclass(frozen=True)
class ProjectArchiveResult:
    path: Path
    dataset_count: int
    source_count: int
    image_count: int


@dataclass(frozen=True)
class ProjectRestoreResult:
    project_id: int
    project_name: str
    source_count: int
    image_count: int
    backup_path: Path | None


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_. " else "_" for ch in value).strip()
    return cleaned or "PetroLab_project"


def _project_record(project_id: int) -> dict:
    for project in list_projects():
        if int(project["id"]) == int(project_id):
            return project
    raise KeyError(f"Проект {project_id} не найден")


def _unique_existing_paths(values: list[str]) -> list[Path]:
    result: list[Path] = []
    seen: set[Path] = set()
    for value in values:
        if not value:
            continue
        path = Path(value).expanduser()
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if not resolved.exists() or not resolved.is_file() or resolved in seen:
            continue
        seen.add(resolved)
        result.append(resolved)
    return result


def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def _project_owned_ids(con: sqlite3.Connection, table: str, project_id: int) -> set[int]:
    tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if table not in tables or "project_id" not in _table_columns(con, table):
        return set()
    return {int(row[0]) for row in con.execute(f"SELECT id FROM {table} WHERE project_id=?", (int(project_id),)).fetchall()}


def _delete_refs_outside(con: sqlite3.Connection, table: str, column: str, allowed: set[int] | set[str]) -> None:
    if allowed:
        marks = ",".join("?" for _ in allowed)
        con.execute(
            f"DELETE FROM {table} WHERE {column} IS NOT NULL AND {column} NOT IN ({marks})",
            tuple(allowed),
        )
    else:
        con.execute(f"DELETE FROM {table} WHERE {column} IS NOT NULL")


def _project_database_snapshot(project_id: int, target: Path) -> None:
    """Copy DB and retain only rows belonging to one project and its child entities.

    Global rows with nullable project_id are intentionally retained because global styles or
    classifications may be required by the selected project's saved recipes. Child tables are
    scoped by their owning Sample/Study/Session/Dataset/Analysis/Rock/Asset IDs, preventing
    metadata from another project leaking into a portable archive.
    """
    shutil.copy2(DB_PATH, target)
    con = sqlite3.connect(target)
    try:
        con.execute("PRAGMA foreign_keys=OFF")
        table_names = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}

        dataset_ids = _project_owned_ids(con, "datasets", project_id)
        sample_ids = _project_owned_ids(con, "samples", project_id)
        study_ids = _project_owned_ids(con, "studies", project_id)
        session_ids = _project_owned_ids(con, "analytical_sessions", project_id)
        rock_ids = _project_owned_ids(con, "rock_samples", project_id)
        asset_ids = _project_owned_ids(con, "image_assets", project_id)

        analysis_ids: set[str] = set()
        if "analysis_rows" in table_names and dataset_ids:
            marks = ",".join("?" for _ in dataset_ids)
            analysis_ids = {
                str(row[0]) for row in con.execute(
                    f"SELECT analysis_id FROM analysis_rows WHERE dataset_id IN ({marks})",
                    tuple(dataset_ids),
                ).fetchall()
            }

        tables = [
            str(row[0]) for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        reference_scopes: tuple[tuple[str, set], ...] = (
            ("dataset_id", dataset_ids),
            ("analysis_id", analysis_ids),
            ("sample_id", sample_ids),
            ("study_id", study_ids),
            ("session_id", session_ids),
            ("rock_id", rock_ids),
            ("asset_id", asset_ids),
        )
        for table in tables:
            columns = _table_columns(con, table)
            if table == "projects":
                con.execute("DELETE FROM projects WHERE id<>?", (int(project_id),))
                continue
            if "project_id" in columns:
                con.execute(
                    f"DELETE FROM {table} WHERE project_id IS NOT NULL AND project_id<>?",
                    (int(project_id),),
                )
                continue
            for column, allowed in reference_scopes:
                if column in columns:
                    _delete_refs_outside(con, table, column, allowed)
                    break
        con.commit()
    finally:
        con.close()


def _optimized_image_bytes(path: Path) -> tuple[bytes, str]:
    """Create a clearly derivative, portable preview without modifying the original."""
    with Image.open(path) as image:
        image = image.convert("RGB")
        image.thumbnail((2400, 2400))
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=88, optimize=True)
        return buffer.getvalue(), ".jpg"


def create_project_archive(
    project_id: int,
    destination: str | Path,
    *,
    mode: ArchiveMode = "full",
    image_mode: ImageMode = "originals",
) -> ProjectArchiveResult:
    """Create a portable single-file .petrolab archive for exactly one project."""
    if mode not in {"project", "project_sources", "full"}:
        raise ValueError(f"Неизвестный режим архива: {mode}")
    if image_mode not in {"none", "optimized", "originals"}:
        raise ValueError(f"Неизвестный режим изображений: {image_mode}")

    ensure_storage()
    project = _project_record(int(project_id))
    datasets = list_datasets(int(project_id))
    target = Path(destination).expanduser()
    if target.suffix.lower() != ".petrolab":
        target = target.with_suffix(".petrolab")
    target.parent.mkdir(parents=True, exist_ok=True)

    source_paths = _unique_existing_paths([
        str(dataset.get("source_path") or "") for dataset in datasets
    ]) if mode in {"project_sources", "full"} else []

    image_paths: list[Path] = []
    project_assets_dir = ASSETS_DIR / f"project_{int(project_id)}"
    if mode == "full" and image_mode != "none" and project_assets_dir.exists():
        image_paths = [path for path in project_assets_dir.rglob("*") if path.is_file()]

    source_map = []
    for index, path in enumerate(source_paths, start=1):
        source_map.append({"archive_name": f"{index:03d}_{_safe_name(path.name)}", "original_name": path.name})

    manifest = {
        "format": "petrolab-project-archive",
        "format_version": 2,
        "project": {
            "id": int(project["id"]), "name": project["name"], "description": project.get("description", ""),
        },
        "mode": mode,
        "image_mode": image_mode,
        "dataset_count": len(datasets),
        "source_files": source_map,
        "image_count": len(image_paths),
        "optimized_images_are_derivatives": image_mode == "optimized",
    }

    with tempfile.TemporaryDirectory(prefix="petrolab_archive_") as temp_dir:
        root = Path(temp_dir)
        database_dir = root / "database"
        database_dir.mkdir(parents=True, exist_ok=True)
        _project_database_snapshot(int(project_id), database_dir / DB_PATH.name)
        (root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        if source_paths:
            source_dir = root / "sources"
            source_dir.mkdir(parents=True, exist_ok=True)
            for path, mapping in zip(source_paths, source_map):
                shutil.copy2(path, source_dir / mapping["archive_name"])

        if image_paths:
            image_root = root / "images"
            for path in image_paths:
                relative = path.relative_to(project_assets_dir)
                destination_path = image_root / relative
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                if image_mode == "optimized":
                    try:
                        data, suffix = _optimized_image_bytes(path)
                        destination_path = destination_path.with_suffix(suffix)
                        destination_path.write_bytes(data)
                    except Exception:
                        continue
                else:
                    shutil.copy2(path, destination_path)

        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in root.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(root))

    return ProjectArchiveResult(target.resolve(), len(datasets), len(source_paths), len(image_paths))


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    root = destination.resolve()
    for member in archive.infolist():
        candidate = (destination / member.filename).resolve()
        if root not in candidate.parents and candidate != root:
            raise ValueError("Архив содержит небезопасный путь")
    archive.extractall(destination)


def _workspace_backup() -> Path | None:
    if not DB_PATH.exists():
        return None
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = BACKUPS_DIR / f"before_project_restore_{stamp}.sqlite3"
    shutil.copy2(DB_PATH, target)
    return target


def restore_project_archive(
    archive_path: str | Path,
    *,
    allow_replace_workspace: bool = False,
) -> ProjectRestoreResult:
    """Restore a .petrolab archive into this PetroLab workspace.

    Default safety policy only allows restore into an empty workspace. Explicit replacement
    first creates a database backup. This avoids silent merging of incompatible local IDs.
    """
    source = Path(archive_path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(source)
    ensure_storage()
    existing_projects = list_projects()
    if existing_projects and not allow_replace_workspace:
        raise ValueError("В текущем PetroLab уже есть проекты. Для восстановления нужен пустой workspace или явное подтверждение замены.")

    with tempfile.TemporaryDirectory(prefix="petrolab_restore_") as temp_dir:
        root = Path(temp_dir)
        with zipfile.ZipFile(source, "r") as archive:
            _safe_extract(archive, root)
        manifest_path = root / "manifest.json"
        if not manifest_path.exists():
            raise ValueError("В архиве отсутствует manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("format") != "petrolab-project-archive" or int(manifest.get("format_version", 0)) not in {1, 2}:
            raise ValueError("Неподдерживаемый формат архива PetroLab")
        archived_db = root / "database" / DB_PATH.name
        if not archived_db.exists():
            raise ValueError("В архиве отсутствует база PetroLab")
        project = manifest.get("project") or {}
        project_id = int(project["id"])

        con = sqlite3.connect(archived_db)
        try:
            check = con.execute("PRAGMA integrity_check").fetchone()[0]
            if check != "ok":
                raise ValueError(f"Архивная база повреждена: {check}")
        finally:
            con.close()

        backup = _workspace_backup() if existing_projects else None
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy2(archived_db, DB_PATH)

        restored_sources = DATA_DIR / f"project_{project_id}" / "restored_sources"
        restored_sources.mkdir(parents=True, exist_ok=True)
        source_dir = root / "sources"
        source_count = 0
        if source_dir.exists():
            for file in source_dir.iterdir():
                if file.is_file():
                    shutil.copy2(file, restored_sources / file.name)
                    source_count += 1

        restored_assets = ASSETS_DIR / f"project_{project_id}"
        image_root = root / "images"
        image_count = 0
        if image_root.exists():
            for file in image_root.rglob("*"):
                if file.is_file():
                    relative = file.relative_to(image_root)
                    target = restored_assets / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file, target)
                    image_count += 1

        con = sqlite3.connect(DB_PATH)
        try:
            con.row_factory = sqlite3.Row
            if restored_sources.exists():
                files = [p for p in restored_sources.iterdir() if p.is_file()]
                datasets = con.execute("SELECT id, source_filename FROM datasets WHERE project_id=?", (project_id,)).fetchall()
                for row in datasets:
                    name = str(row["source_filename"] or "")
                    matches = [p for p in files if p.name.endswith(name)]
                    if len(matches) == 1:
                        con.execute("UPDATE datasets SET source_path=? WHERE id=?", (str(matches[0].resolve()), int(row["id"])))
            if restored_assets.exists():
                asset_files = [p for p in restored_assets.rglob("*") if p.is_file()]
                records = con.execute("SELECT id, stored_path FROM image_assets WHERE project_id=?", (project_id,)).fetchall()
                for row in records:
                    old = Path(str(row["stored_path"] or ""))
                    exact = [p for p in asset_files if p.name == old.name]
                    if len(exact) == 1:
                        target = exact[0]
                    else:
                        same_stem = [p for p in asset_files if p.stem == old.stem]
                        target = same_stem[0] if len(same_stem) == 1 else None
                    if target is not None:
                        con.execute("UPDATE image_assets SET stored_path=? WHERE id=?", (str(target.resolve()), int(row["id"])))
            con.commit()
        finally:
            con.close()

    ensure_storage()
    return ProjectRestoreResult(project_id, str(project.get("name") or "PetroLab project"), source_count, image_count, backup)
