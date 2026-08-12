from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path

import openpyxl

from .db import BACKUPS_DIR, get_dataset, update_source_hash_for_path
from .io_utils import read_tabular_path, sha256_file


def source_status(dataset: dict) -> tuple[str, str]:
    path_text = dataset.get("source_path") or ""
    if not path_text:
        return "несвязанный", "Исходник был загружен через браузер; абсолютный путь к пользовательскому файлу неизвестен."
    path = Path(path_text)
    if not path.exists():
        return "не найден", str(path)
    current_hash = sha256_file(path)
    if current_hash == dataset.get("source_sha256"):
        return "актуален", str(path)
    return "изменён вне ПетроЛаба", str(path)


def backup_source(path: str | Path, dataset_id: int) -> Path:
    path = Path(path)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    target_dir = BACKUPS_DIR / f"dataset_{dataset_id}"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, target)
    return target


def validate_sync_change(dataset: dict, change: dict) -> None:
    if not dataset.get("sync_enabled"):
        raise ValueError(f"Набор «{dataset['name']}»: обратная запись в источник отключена")

    path_text = dataset.get("source_path") or ""
    if not path_text:
        raise ValueError(f"Набор «{dataset['name']}»: нет связанного локального файла")
    path = Path(path_text)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("Обратная запись поддерживается только для XLSX и XLSM")

    source_row = change.get("source_row")
    if source_row is None:
        raise ValueError(f"У анализа {change['analysis_id']} не сохранена строка источника")

    mapping = json.loads(dataset.get("column_map_json") or "{}")
    column = change["column_name"]
    if column not in mapping:
        raise ValueError(
            f"Набор «{dataset['name']}»: колонка «{column}» не связана с исходной колонкой Excel"
        )
    info = mapping[column]
    if not isinstance(info, dict) or "column_index" not in info:
        raise ValueError(f"Набор «{dataset['name']}»: повреждена карта колонки «{column}»")
    _to_source_value(info, change.get("new_value"), column)


def _to_source_value(info: dict, value: object, column_name: str) -> object:
    """Convert a canonical PetroLab value back to the source column's original unit."""
    factor = float(info.get("to_source_factor", 1.0) or 1.0)
    if factor == 1.0 or value is None or value == "":
        return value
    try:
        return float(value) * factor
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Колонка «{column_name}» имеет преобразование единиц; значение должно быть числом"
        ) from exc


def sync_workbook_changes(dataset_changes: list[tuple[dict, list[dict]]]) -> str:
    if not dataset_changes:
        raise ValueError("Нет изменений для записи")

    first_dataset = dataset_changes[0][0]
    path = Path(first_dataset.get("source_path") or "")
    if not path:
        raise ValueError("Не указан путь к источнику")

    resolved = path.resolve()
    for dataset, changes in dataset_changes:
        dataset_path = Path(dataset.get("source_path") or "").resolve()
        if dataset_path != resolved:
            raise ValueError("В одну операцию sync_workbook_changes переданы разные файлы")
        for change in changes:
            validate_sync_change(dataset, change)

    backup = backup_source(path, int(first_dataset["id"]))
    keep_vba = path.suffix.lower() == ".xlsm"
    workbook = openpyxl.load_workbook(path, keep_vba=keep_vba)
    temp = path.with_name(path.stem + ".petrolab_tmp" + path.suffix)

    try:
        for dataset, changes in dataset_changes:
            mapping = json.loads(dataset.get("column_map_json") or "{}")
            sheet_name = dataset.get("source_sheet") or None
            worksheet = workbook[sheet_name] if sheet_name else workbook.active
            for change in changes:
                info = mapping[change["column_name"]]
                worksheet.cell(
                    row=int(change["source_row"]),
                    column=int(info["column_index"]),
                    value=_to_source_value(info, change["new_value"], change["column_name"]),
                )
        workbook.save(temp)
    finally:
        workbook.close()

    os.replace(temp, path)
    new_hash = sha256_file(path)
    update_source_hash_for_path(str(path), new_hash)
    return str(backup)


def restore_source_backup(source_path: str | Path, backup_path: str | Path) -> None:
    source = Path(source_path)
    backup = Path(backup_path)
    if not backup.exists():
        raise FileNotFoundError(backup)
    shutil.copy2(backup, source)
    update_source_hash_for_path(str(source), sha256_file(source))


def sync_cell_changes(dataset: dict, changes: list[dict]) -> str:
    return sync_workbook_changes([(dataset, changes)])


def reload_linked_source(dataset_id: int):
    dataset = get_dataset(dataset_id)
    path_text = dataset.get("source_path") or ""
    if not path_text:
        raise ValueError("Набор не связан с локальным файлом")
    path = Path(path_text)
    df, mapping, source_rows = read_tabular_path(
        path,
        sheet_name=dataset.get("source_sheet") or None,
        header_row=int(dataset.get("header_row") or 1),
    )
    return df, mapping, source_rows, sha256_file(path)
