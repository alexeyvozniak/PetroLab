from __future__ import annotations

import io
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pandas as pd
from PIL import Image, UnidentifiedImageError

from petrolab.db import ASSETS_DIR, get_analysis_record, get_dataset, load_dataset_dataframe
from petrolab.repositories.image_repository import (
    create_image_record,
    delete_image_record,
    get_image_record,
    list_image_records,
    replace_image_analysis_links,
)

SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
SCOPE_DATASET = "Набор данных"
SCOPE_FIELD = "Значение поля"
SCOPE_ANALYSIS = "Точки анализа"


@dataclass(frozen=True)
class ImagePayload:
    filename: str
    data: bytes


@dataclass(frozen=True)
class ImageScope:
    scope_type: str
    analysis_id: str | None = None
    analysis_ids: tuple[str, ...] = ()
    scope_column: str = ""
    scope_value: str = ""


@dataclass(frozen=True)
class ImageAssignment:
    image: ImagePayload
    scope: ImageScope
    kind: str
    title: str = ""


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
    assignments = [ImageAssignment(image, scope, kind, title) for image in images]
    return create_assigned_image_batch(
        project_id=project_id,
        dataset_id=dataset_id,
        assignments=assignments,
    )


def create_assigned_image_batch(
    *,
    project_id: int,
    dataset_id: int,
    assignments: list[ImageAssignment],
) -> ImageBatchResult:
    """Prevalidate the full batch, then store it with compensating rollback on failure.

    Filesystem writes and SQLite records cannot form one ACID transaction. PetroLab
    therefore validates every image/scope before writing anything and removes all files
    and records already created if a later item fails.
    """
    dataset = _validate_dataset(project_id, dataset_id)
    if not assignments:
        raise ValueError("Не выбрано ни одного изображения")

    normalized: list[ImageAssignment] = []
    for assignment in assignments:
        _validate_payload(assignment.image)
        normalized.append(
            ImageAssignment(
                image=assignment.image,
                scope=_validate_scope(dataset, assignment.scope),
                kind=assignment.kind.strip() or "Другое",
                title=assignment.title.strip(),
            )
        )

    asset_dir = ASSETS_DIR / f"project_{int(project_id)}" / f"dataset_{int(dataset_id)}"
    asset_dir.mkdir(parents=True, exist_ok=True)
    created_paths: list[Path] = []
    created_ids: list[int] = []
    try:
        for assignment in normalized:
            target = _write_image_file(asset_dir, assignment.image)
            created_paths.append(target)
            analysis_ids = _analysis_ids(assignment.scope)
            asset_id = create_image_record(
                project_id=int(project_id),
                dataset_id=int(dataset_id),
                analysis_ids=analysis_ids,
                scope_type=assignment.scope.scope_type,
                scope_column=assignment.scope.scope_column,
                scope_value=assignment.scope.scope_value,
                kind=assignment.kind,
                title=assignment.title,
                original_filename=Path(assignment.image.filename).name,
                stored_path=str(target),
            )
            created_ids.append(asset_id)
    except Exception:
        _cleanup_created(created_ids, created_paths)
        raise
    return ImageBatchResult(tuple(created_ids))


def relink_image_asset(asset_id: int, analysis_ids: list[str]) -> None:
    """Repair an existing image by assigning it to valid points in its own dataset."""
    record = get_image_record(int(asset_id))
    dataset = get_dataset(int(record["dataset_id"]))
    scope = _validate_analysis_scope(
        dataset,
        ImageScope(SCOPE_ANALYSIS, analysis_ids=tuple(str(value) for value in analysis_ids)),
    )
    replace_image_analysis_links(int(asset_id), _analysis_ids(scope))


def delete_image_asset(asset_id: int) -> None:
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


def list_all_images() -> list[dict]:
    return list_image_records()


def image_export_records() -> list[dict]:
    exported: list[dict] = []
    for record in list_image_records():
        row = dict(record)
        row["analysis_ids"] = "; ".join(str(value) for value in (row.get("analysis_ids") or []))
        exported.append(row)
    return exported


def related_images_for_row(selected_row: pd.Series, project_id: int | None = None) -> list[dict]:
    dataset_id = int(selected_row.get("_dataset_id"))
    assets = list_image_records(project_id=project_id, dataset_id=dataset_id)
    analysis_id = str(selected_row.get("_analysis_id"))
    related: list[dict] = []
    for asset in assets:
        if analysis_id in set(asset.get("analysis_ids") or []):
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


def _analysis_ids(scope: ImageScope) -> tuple[str, ...]:
    values = list(scope.analysis_ids)
    if scope.analysis_id:
        values.append(scope.analysis_id)
    return tuple(dict.fromkeys(str(value) for value in values if value))


def _validate_analysis_scope(dataset: dict, scope: ImageScope) -> ImageScope:
    analysis_ids = _analysis_ids(scope)
    if not analysis_ids:
        raise ValueError("Не выбрана ни одна аналитическая точка")
    for analysis_id in analysis_ids:
        record = get_analysis_record(analysis_id)
        if int(record["dataset_id"]) != int(dataset["id"]):
            raise ValueError(f"Аналитическая точка {analysis_id[:8]} относится к другому набору")
    return ImageScope(
        SCOPE_ANALYSIS,
        analysis_id=analysis_ids[0] if len(analysis_ids) == 1 else None,
        analysis_ids=analysis_ids,
    )


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
    try:
        with Image.open(io.BytesIO(image.data)) as opened:
            opened.verify()
    except (UnidentifiedImageError, OSError, SyntaxError) as exc:
        raise ValueError(f"Файл {filename} не является читаемым изображением или повреждён") from exc


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
