from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from petrolab.db import get_dataset, update_analysis_values
from petrolab.sources import restore_source_backup, sync_workbook_changes, validate_sync_change


@dataclass
class SaveResult:
    saved_changes: int = 0
    synced_files: int = 0
    backup_paths: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def save_changes_to_database(changes: list[dict[str, Any]]) -> SaveResult:
    """Save pending analysis edits only to PetroLab's database."""
    if not changes:
        return SaveResult()
    update_analysis_values(changes, synced_to_source=False)
    return SaveResult(saved_changes=len(changes))


def _group_by_source(changes: list[dict[str, Any]]) -> dict[Path, list[tuple[dict, list[dict[str, Any]]]]]:
    by_dataset: dict[int, list[dict[str, Any]]] = {}
    for change in changes:
        by_dataset.setdefault(int(change["dataset_id"]), []).append(change)

    grouped: dict[Path, list[tuple[dict, list[dict[str, Any]]]]] = {}
    for dataset_id, dataset_changes in by_dataset.items():
        dataset = get_dataset(dataset_id)
        for change in dataset_changes:
            validate_sync_change(dataset, change)
        path = Path(dataset["source_path"]).resolve()
        grouped.setdefault(path, []).append((dataset, dataset_changes))
    return grouped


def save_changes_and_sync(changes: list[dict[str, Any]]) -> SaveResult:
    """Persist edits to all linked workbooks and then to the PetroLab database.

    The operation performs a full preflight before touching files. Each physical
    workbook gets one backup and one save, even if several datasets/sheets from
    that workbook are edited. If a later workbook fails, earlier workbooks are
    restored from their backups before the error is returned.
    """
    if not changes:
        return SaveResult()

    try:
        grouped = _group_by_source(changes)
    except Exception as exc:
        return SaveResult(errors=[str(exc)])

    completed: list[tuple[Path, str, list[dict[str, Any]]]] = []
    try:
        for source_path, dataset_changes in grouped.items():
            workbook_changes = [change for _, group in dataset_changes for change in group]
            backup = sync_workbook_changes(dataset_changes)
            completed.append((source_path, backup, workbook_changes))
    except Exception as exc:
        rollback_errors: list[str] = []
        for source_path, backup, _ in reversed(completed):
            try:
                restore_source_backup(source_path, backup)
            except Exception as rollback_exc:
                rollback_errors.append(f"Не удалось восстановить {source_path.name}: {rollback_exc}")
        errors = [f"Синхронизация отменена: {exc}"] + rollback_errors
        return SaveResult(errors=errors)

    try:
        for _, backup, workbook_changes in completed:
            update_analysis_values(
                workbook_changes,
                synced_to_source=True,
                source_backup=backup,
            )
    except Exception as exc:
        rollback_errors: list[str] = []
        for source_path, backup, _ in reversed(completed):
            try:
                restore_source_backup(source_path, backup)
            except Exception as rollback_exc:
                rollback_errors.append(f"Не удалось восстановить {source_path.name}: {rollback_exc}")
        errors = [
            "Excel-файлы восстановлены, но сохранение журнала/базы завершилось ошибкой: " + str(exc)
        ] + rollback_errors
        return SaveResult(errors=errors)

    return SaveResult(
        saved_changes=len(changes),
        synced_files=len(completed),
        backup_paths=[backup for _, backup, _ in completed],
    )
