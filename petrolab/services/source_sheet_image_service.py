from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from petrolab.db import ASSETS_DIR, dataset_is_accessible, get_analysis_record, get_dataset
from petrolab.repositories.image_repository import create_image_record
from petrolab.services.image_service import (
    ImageAssignment,
    ImageBatchResult,
    ImageScope,
    SCOPE_ANALYSIS,
    _analysis_ids,
    _cleanup_created,
    _validate_payload,
    _write_image_file,
)
from petrolab.source_sheet_scope import source_sheet_scope_for_dataset


def _validate_source_sheet_analysis_scope(
    project_id: int,
    anchor_dataset_id: int,
    scope: ImageScope,
) -> ImageScope:
    analysis_ids = _analysis_ids(scope)
    if not analysis_ids:
        raise ValueError("Не выбрана ни одна аналитическая точка")

    sheet = source_sheet_scope_for_dataset(int(project_id), int(anchor_dataset_id))
    if sheet is None:
        raise ValueError("Не удалось восстановить исходный лист для выбранного набора")
    allowed = set(int(value) for value in sheet.dataset_ids)

    for analysis_id in analysis_ids:
        record = get_analysis_record(str(analysis_id))
        dataset_id = int(record["dataset_id"])
        if dataset_id not in allowed:
            raise ValueError(
                f"Точка {str(analysis_id)[:8]} относится к другому исходному листу"
            )
        if not dataset_is_accessible(int(project_id), dataset_id):
            raise ValueError("Одна из выбранных точек недоступна в активном проекте")

    return ImageScope(
        SCOPE_ANALYSIS,
        analysis_id=analysis_ids[0] if len(analysis_ids) == 1 else None,
        analysis_ids=analysis_ids,
    )


def create_source_sheet_image_batch(
    *,
    project_id: int,
    anchor_dataset_id: int,
    assignments: list[ImageAssignment],
) -> ImageBatchResult:
    """Store images against one source-sheet anchor while allowing links to all sibling phase datasets.

    The asset itself still has one stable dataset_id for backwards compatibility. Analysis links may
    cross phase datasets only when every selected analysis belongs to the same immutable source sheet.
    """
    anchor = get_dataset(int(anchor_dataset_id))
    if not dataset_is_accessible(int(project_id), int(anchor_dataset_id)):
        raise ValueError("Исходный лист не добавлен в активный проект")
    if not assignments:
        raise ValueError("Не выбрано ни одного изображения")

    normalized: list[ImageAssignment] = []
    for assignment in assignments:
        _validate_payload(assignment.image)
        scope = assignment.scope
        if scope.scope_type != SCOPE_ANALYSIS:
            raise ValueError(
                "Для привязки по исходному листу выберите конкретные аналитические точки"
            )
        normalized.append(
            replace(
                assignment,
                scope=_validate_source_sheet_analysis_scope(
                    int(project_id), int(anchor_dataset_id), scope
                ),
                kind=assignment.kind.strip() or "Другое",
                title=assignment.title.strip(),
            )
        )

    asset_dir = ASSETS_DIR / f"project_{int(project_id)}" / f"dataset_{int(anchor['id'])}"
    asset_dir.mkdir(parents=True, exist_ok=True)
    created_paths: list[Path] = []
    created_ids: list[int] = []
    try:
        for assignment in normalized:
            target = _write_image_file(asset_dir, assignment.image)
            created_paths.append(target)
            asset_id = create_image_record(
                project_id=int(project_id),
                dataset_id=int(anchor_dataset_id),
                analysis_ids=_analysis_ids(assignment.scope),
                scope_type=assignment.scope.scope_type,
                scope_column=assignment.scope.scope_column,
                scope_value=assignment.scope.scope_value,
                kind=assignment.kind,
                title=assignment.title,
                original_filename=Path(assignment.image.filename).name,
                stored_path=str(target),
            )
            created_ids.append(int(asset_id))
    except Exception:
        _cleanup_created(created_ids, created_paths)
        raise
    return ImageBatchResult(tuple(created_ids))
