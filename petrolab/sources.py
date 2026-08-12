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


def sync_cell_changes(dataset: dict, changes: list[dict]) -> str:
    """Записывает изменения конкретных ячеек в связанный XLSX/XLSM. Возвращает путь к backup."""
    path_text = dataset.get("source_path") or ""
    if not path_text:
        raise ValueError("У набора нет связанного локального файла")
    path = Path(path_text)
    if not path.exists():
        raise FileNotFoundError(path)
    if path.suffix.lower() not in {".xlsx", ".xlsm"}:
        raise ValueError("Обратная запись сейчас поддерживается только для XLSX и XLSM")

    mapping = json.loads(dataset.get("column_map_json") or "{}")
    sheet_name = dataset.get("source_sheet") or None
    keep_vba = path.suffix.lower() == ".xlsm"
    backup = backup_source(path, int(dataset["id"]))
    wb = openpyxl.load_workbook(path, keep_vba=keep_vba)
    ws = wb[sheet_name] if sheet_name else wb.active

    for ch in changes:
        source_row = ch.get("source_row")
        col = ch["column_name"]
        if source_row is None:
            raise ValueError(f"У анализа {ch['analysis_id']} не сохранена строка источника")
        info = mapping.get(col)
        if not info:
            raise ValueError(f"Колонка «{col}» не связана с исходной колонкой Excel")
        ws.cell(row=int(source_row), column=int(info["column_index"]), value=ch["new_value"])

    temp = path.with_name(path.stem + ".petrolab_tmp" + path.suffix)
    wb.save(temp)
    wb.close()
    os.replace(temp, path)
    new_hash = sha256_file(path)
    update_source_hash_for_path(str(path), new_hash)
    return str(backup)


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
