from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from petrolab.db import _json_safe_record, connect, get_dataset, load_dataset_dataframe
from petrolab.io_utils import add_qc_columns
from petrolab.repositories.analysis_repository import apply_analysis_changes
from petrolab.sources import restore_source_backup, sync_workbook_changes, validate_sync_change

_GENERATED_QC_COLUMNS = (
    "Σ компонентов raw", "Поправка O=F,Cl", "Σ corrected", "Σ оксидов",
    "QC суммы", "QC химии", "QC железа", "QC уровень", "QC причины",
)
_DATABASE_ONLY_COLUMNS = {"QC решение"}


@dataclass
class SaveResult:
    saved_changes: int = 0
    synced_files: int = 0
    backup_paths: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _affected(changes: list[dict[str, Any]]) -> tuple[set[str], set[int]]:
    analysis_ids = {str(change["analysis_id"]) for change in changes}
    dataset_ids = {int(change["dataset_id"]) for change in changes}
    return analysis_ids, dataset_ids


def _refresh_generated_qc(changes: list[dict[str, Any]]) -> list[str]:
    analysis_ids, _ = _affected(changes)
    if not analysis_ids:
        return []
    warnings: list[str] = []
    with connect() as con:
        try:
            for analysis_id in sorted(analysis_ids):
                row = con.execute(
                    "SELECT data_json FROM analysis_rows WHERE analysis_id=?",
                    (analysis_id,),
                ).fetchone()
                if row is None:
                    continue
                data = json.loads(row["data_json"])
                refreshed = add_qc_columns(pd.DataFrame([data]))
                if refreshed.empty:
                    continue
                values = _json_safe_record(refreshed.iloc[0].to_dict())
                for column in _GENERATED_QC_COLUMNS:
                    if column in values:
                        data[column] = values[column]
                    else:
                        data.pop(column, None)
                # Generated QC follows the already-saved chemistry but must not create
                # another source edit, change-log event, or formula freshness timestamp.
                con.execute(
                    "UPDATE analysis_rows SET data_json=? WHERE analysis_id=?",
                    (json.dumps(_json_safe_record(data), ensure_ascii=False), analysis_id),
                )
            con.commit()
        except Exception as exc:
            con.rollback()
            warnings.append(f"Не удалось обновить generated QC после сохранения: {exc}")
    return warnings


def _refresh_recovery_snapshots(changes: list[dict[str, Any]]) -> list[str]:
    _, dataset_ids = _affected(changes)
    warnings: list[str] = []
    for dataset_id in sorted(dataset_ids):
        try:
            dataset = get_dataset(dataset_id)
            target_text = str(dataset.get("csv_path") or "").strip()
            if not target_text:
                continue
            target = Path(target_text)
            target.parent.mkdir(parents=True, exist_ok=True)
            dataframe = load_dataset_dataframe(dataset_id, include_meta=False)
            temp = target.with_name(target.name + ".petrolab_tmp")
            try:
                dataframe.to_csv(temp, index=False, encoding="utf-8-sig")
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)
        except Exception as exc:
            warnings.append(
                f"Dataset {dataset_id}: база сохранена, но recovery snapshot не обновлён: {exc}"
            )
    return warnings


def _post_save_maintenance(changes: list[dict[str, Any]]) -> list[str]:
    warnings = _refresh_generated_qc(changes)
    warnings.extend(_refresh_recovery_snapshots(changes))
    return warnings


def save_changes_to_database(changes: list[dict[str, Any]]) -> SaveResult:
    """Save pending analysis edits to SQLite, then refresh generated QC and recovery CSV."""
    if not changes:
        return SaveResult()
    try:
        apply_analysis_changes(changes, synced_to_source=False)
    except Exception as exc:
        return SaveResult(errors=[str(exc)])
    return SaveResult(
        saved_changes=len(changes),
        warnings=_post_save_maintenance(changes),
    )


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

    The service validates every change before touching a file. Every physical workbook
    gets one backup and one save. SQLite source edits are committed only after workbook
    writes succeed; generated QC and recovery snapshots are refreshed afterwards without
    changing source-edit timestamps.
    """
    if not changes:
        return SaveResult()

    source_changes = [change for change in changes if str(change.get("column_name")) not in _DATABASE_ONLY_COLUMNS]
    database_only = [change for change in changes if str(change.get("column_name")) in _DATABASE_ONLY_COLUMNS]
    if not source_changes:
        result = save_changes_to_database(database_only)
        result.warnings.append("Решение QC сохранено только в PetroLab; исходный Excel не изменялся.")
        return result

    try:
        grouped = _group_by_source(source_changes)
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
    transactional_changes.extend(database_only)

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
        warnings=_post_save_maintenance(transactional_changes),
    )
