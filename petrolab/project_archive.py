from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from petrolab.db import ASSETS_DIR, DB_PATH, DATA_DIR, get_project, list_datasets

ArchiveMode = Literal["project", "project_sources", "full"]
ImageMode = Literal["none", "originals"]


@dataclass(frozen=True)
class ProjectArchiveResult:
    path: Path
    dataset_count: int
    source_count: int
    image_count: int


def _safe_name(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "-_. " else "_" for ch in value).strip()
    return cleaned or "PetroLab_project"


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


def create_project_archive(
    project_id: int,
    destination: str | Path,
    *,
    mode: ArchiveMode = "full",
    image_mode: ImageMode = "originals",
) -> ProjectArchiveResult:
    """Create a portable single-file .petrolab archive for one project.

    The archive always contains the PetroLab database snapshot and a manifest. Source
    workbooks are included in project_sources/full modes. Image assets are included
    only in full mode and only when image_mode is originals.
    """
    if mode not in {"project", "project_sources", "full"}:
        raise ValueError(f"Неизвестный режим архива: {mode}")
    if image_mode not in {"none", "originals"}:
        raise ValueError(f"Неизвестный режим изображений: {image_mode}")

    project = get_project(int(project_id))
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
    if mode == "full" and image_mode == "originals" and project_assets_dir.exists():
        image_paths = [path for path in project_assets_dir.rglob("*") if path.is_file()]

    manifest = {
        "format": "petrolab-project-archive",
        "format_version": 1,
        "project": {
            "id": int(project["id"]),
            "name": project["name"],
            "description": project.get("description", ""),
        },
        "mode": mode,
        "image_mode": image_mode,
        "dataset_count": len(datasets),
        "source_files": [path.name for path in source_paths],
        "image_count": len(image_paths),
        "restore_note": (
            "Архив содержит снимок всей SQLite-базы PetroLab. При восстановлении на другом "
            "компьютере используйте функцию восстановления проекта, а не распаковывайте файлы вручную."
        ),
    }

    with tempfile.TemporaryDirectory(prefix="petrolab_archive_") as temp_dir:
        root = Path(temp_dir)
        database_dir = root / "database"
        database_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DB_PATH, database_dir / DB_PATH.name)

        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        if source_paths:
            source_dir = root / "sources"
            source_dir.mkdir(parents=True, exist_ok=True)
            for index, path in enumerate(source_paths, start=1):
                shutil.copy2(path, source_dir / f"{index:03d}_{_safe_name(path.name)}")

        if image_paths:
            image_root = root / "images"
            for path in image_paths:
                relative = path.relative_to(project_assets_dir)
                destination_path = image_root / relative
                destination_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination_path)

        with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for path in root.rglob("*"):
                if path.is_file():
                    archive.write(path, path.relative_to(root))

    return ProjectArchiveResult(
        path=target.resolve(),
        dataset_count=len(datasets),
        source_count=len(source_paths),
        image_count=len(image_paths),
    )
