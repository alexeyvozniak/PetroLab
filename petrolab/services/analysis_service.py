from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from petrolab.db import get_dataset
from petrolab.repositories.analysis_repository import apply_analysis_changes
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
    try:
        apply_analysis_changes(changes, synced_to_source=False)
    except Exception as exc:
        return SaveResult(errors=[str(exc)])
    return SaveResult(saved_changes=len(changes))


def _group_by_source(
    changes: list[dict[str, Any]],
) -> dict[Path, list[tuple[dict, list[dict[str, Any]]]]]:
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


def _rollback_completed(completed: list[tuple[Path, str, list[dict[str, Any]]]]) -> list[str]:
    errors: list[str] = []
    for source_path, backup, _ in reversed(completed):
        try:
            restore_source_backup(source_path, backup)
        except Exception as exc:
            errors.append(f"Не удалось восстановить {source_path.name}: {exc}")
    return errors


def save_changes_and_sync(changes: list[dict[str, Any]]) -> SaveResult:
    """Persist an edit batch to linked workbooks and SQLite consistently.

    The service validates every change before touching a file. Every physical
    workbook gets one backup and one save, even when several datasets/sheets are
    involved. SQLite updates are committed in one transaction only after all
    workbook writes succeed. If workbook or database persistence fails, already
    modified workbooks are restored from their backups.
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
        errors = [f"Синхронизация отменена: {exc}"] + _rollback_completed(completed)
        return SaveResult(errors=errors)

    transactional_changes: list[dict[str, Any]] = []
    for _, backup, workbook_changes in completed:
        for change in workbook_changes:
            transactional_changes.append({**change, "source_backup": backup})

    try:
        apply_analysis_changes(transactional_changes, synced_to_source=True)
    except Exception as exc:
        errors = [
            "Excel-файлы восстановлены, а изменения в базе не зафиксированы: " + str(exc)
        ] + _rollback_completed(completed)
        return SaveResult(errors=errors)

    return SaveResult(
        saved_changes=len(changes),
        synced_files=len(completed),
        backup_paths=[backup for _, backup, _ in completed],
    )
