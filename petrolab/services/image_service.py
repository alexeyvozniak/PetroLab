from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pandas as pd

from petrolab.db import ASSETS_DIR, get_analysis_record, get_dataset, load_dataset_dataframe
from petrolab.repositories.image_repository import (
    create_image_record,
    delete_image_record,
    get_image_record,
    list_image_records,
)

SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
SCOPE_DATASET = "Набор данных"
SCOPE_FIELD = "Значение поля"
SCOPE_ANALYSIS = "Конкретная точка анализа"


@dataclass(frozen=True)
class ImagePayload:
    filename: str
    data: bytes


@dataclass(frozen=True)
class ImageScope:
    scope_type: str
    analysis_id: str | None = None
    scope_column: str = ""
    scope_value: str = ""


@dataclass(frozen=True)
class ImageBatchResult:
    asset_ids: tuple[int, ...]

    @property
    def count(self) -> int:
        return len(self.asset_ids)


def create_image_assets(
    *,
    project_id: int,
    dataset_id: int,
    images: list[ImagePayload],
    scope: ImageScope,
    kind: str,
    title: str = "",
) -> ImageBatchResult:
    """Validate a batch, store files, and register their metadata."""
    dataset = _validate_dataset(project_id, dataset_id)
    normalized_scope = _validate_scope(dataset, scope)
    if not images:
        raise ValueError("Не выбрано ни одного изображения")
    for image in images:
        _validate_payload(image)

    asset_dir = ASSETS_DIR / f"project_{int(project_id)}" / f"dataset_{int(dataset_id)}"
    asset_dir.mkdir(parents=True, exist_ok=True)
    created_paths: list[Path] = []
    created_ids: list[int] = []
    try:
        for image in images:
            target = _write_image_file(asset_dir, image)
            created_paths.append(target)
            asset_id = create_image_record(
                project_id=int(project_id),
                dataset_id=int(dataset_id),
                analysis_id=normalized_scope.analysis_id,
                scope_type=normalized_scope.scope_type,
                scope_column=normalized_scope.scope_column,
                scope_value=normalized_scope.scope_value,
                kind=kind.strip() or "Другое",
                title=title.strip(),
                original_filename=Path(image.filename).name,
                stored_path=str(target),
            )
            created_ids.append(asset_id)
    except Exception:
        _cleanup_created(created_ids, created_paths)
        raise
    return ImageBatchResult(tuple(created_ids))


def delete_image_asset(asset_id: int) -> None:
    """Remove one asset without leaving a dangling DB record or orphaned user-visible file."""
    record = get_image_record(int(asset_id))
    path = Path(record["stored_path"])
    staged = path.with_name(path.name + ".petrolab_delete")

    if path.exists():
        os.replace(path, staged)
    try:
        delete_image_record(int(asset_id))
    except sqlite3.Error:
        if staged.exists():
            os.replace(staged, path)
        raise
    if staged.exists():
        staged.unlink()


def list_dataset_images(dataset_id: int) -> list[dict]:
    return list_image_records(dataset_id=int(dataset_id))


def related_images_for_row(selected_row: pd.Series, project_id: int | None = None) -> list[dict]:
    """Resolve direct, dataset-level, and field-value image links for one analysis row."""
    dataset_id = int(selected_row.get("_dataset_id"))
    assets = list_image_records(project_id=project_id, dataset_id=dataset_id)
    analysis_id = str(selected_row.get("_analysis_id"))
    related: list[dict] = []
    for asset in assets:
        if asset.get("analysis_id") == analysis_id:
            related.append(asset)
        elif asset.get("scope_type") == SCOPE_DATASET:
            related.append(asset)
        elif asset.get("scope_type") == SCOPE_FIELD:
            column = asset.get("scope_column") or ""
            if column in selected_row.index and str(selected_row.get(column)) == str(asset.get("scope_value")):
                related.append(asset)
    return related


def _validate_dataset(project_id: int, dataset_id: int) -> dict:
    dataset = get_dataset(int(dataset_id))
    if int(dataset["project_id"]) != int(project_id):
        raise ValueError("Набор данных не принадлежит выбранному проекту")
    return dataset


def _validate_scope(dataset: dict, scope: ImageScope) -> ImageScope:
    if scope.scope_type == SCOPE_DATASET:
        return ImageScope(SCOPE_DATASET)
    if scope.scope_type == SCOPE_ANALYSIS:
        return _validate_analysis_scope(dataset, scope)
    if scope.scope_type == SCOPE_FIELD:
        return _validate_field_scope(dataset, scope)
    raise ValueError(f"Неизвестный тип привязки: {scope.scope_type}")


def _validate_analysis_scope(dataset: dict, scope: ImageScope) -> ImageScope:
    if not scope.analysis_id:
        raise ValueError("Не выбрана аналитическая точка")
    record = get_analysis_record(str(scope.analysis_id))
    if int(record["dataset_id"]) != int(dataset["id"]):
        raise ValueError("Аналитическая точка относится к другому набору")
    return ImageScope(SCOPE_ANALYSIS, analysis_id=str(scope.analysis_id))


def _validate_field_scope(dataset: dict, scope: ImageScope) -> ImageScope:
    column = scope.scope_column.strip()
    value = str(scope.scope_value).strip()
    if not column or not value:
        raise ValueError("Нужно выбрать колонку и значение")
    dataframe = load_dataset_dataframe(int(dataset["id"]), include_meta=True)
    if column not in dataframe.columns:
        raise ValueError(f"Колонка «{column}» отсутствует в наборе")
    existing = set(dataframe[column].dropna().astype(str))
    if value not in existing:
        raise ValueError(f"Значение «{value}» отсутствует в колонке «{column}»")
    return ImageScope(SCOPE_FIELD, scope_column=column, scope_value=value)


def _validate_payload(image: ImagePayload) -> None:
    filename = Path(image.filename).name
    if not filename:
        raise ValueError("У изображения отсутствует имя файла")
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_IMAGE_SUFFIXES:
        raise ValueError(f"Неподдерживаемый формат изображения: {suffix}")
    if not image.data:
        raise ValueError(f"Файл {filename} пустой")


def _write_image_file(asset_dir: Path, image: ImagePayload) -> Path:
    suffix = Path(image.filename).suffix.lower()
    target = asset_dir / f"{uuid4().hex}{suffix}"
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_bytes(image.data)
    os.replace(temporary, target)
    return target


def _cleanup_created(asset_ids: list[int], paths: list[Path]) -> None:
    for asset_id in reversed(asset_ids):
        try:
            delete_image_record(asset_id)
        except sqlite3.Error:
            continue
    for path in reversed(paths):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            continue
