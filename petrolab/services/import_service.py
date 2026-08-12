from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pandas as pd

from petrolab.db import (
    DATA_DIR,
    add_dataset,
    get_dataset,
    replace_dataset_rows,
    update_dataset_metadata,
)
from petrolab.io_utils import (
    list_excel_sheets,
    list_excel_sheets_path,
    read_tabular_path,
    read_tabular_with_map,
    sha256_bytes,
    sha256_file,
)
from petrolab.minerals.registry import MINERALS
from petrolab.sources import reload_linked_source

SUPPORTED_SOURCE_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".csv"}
EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls"}
SYNCABLE_SUFFIXES = {".xlsx", ".xlsm"}


@dataclass(frozen=True)
class ImportBatchResult:
    """Result of importing one or more sheets from a single source."""

    dataset_ids: tuple[int, ...]
    source_path: Path

    @property
    def count(self) -> int:
        return len(self.dataset_ids)


def validate_source_path(path: str | Path) -> Path:
    """Return a normalized supported source path or raise a descriptive error."""
    source = Path(path).expanduser()
    if not source.exists():
        raise FileNotFoundError(source)
    if not source.is_file():
        raise ValueError(f"Источник не является файлом: {source}")
    if source.suffix.lower() not in SUPPORTED_SOURCE_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SOURCE_SUFFIXES))
        raise ValueError(f"Неподдерживаемый формат {source.suffix or '(без расширения)'}. Поддерживаются: {supported}")
    return source.resolve()


def list_linked_sheets(path: str | Path) -> list[str]:
    """List importable sheets for a linked source; CSV is represented by an empty sheet name."""
    source = validate_source_path(path)
    if source.suffix.lower() in EXCEL_SUFFIXES:
        return list_excel_sheets_path(source)
    return [""]


def list_uploaded_sheets(file_bytes: bytes, filename: str) -> list[str]:
    """List importable sheets for an uploaded source; CSV has one unnamed sheet."""
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SOURCE_SUFFIXES:
        raise ValueError(f"Неподдерживаемый формат: {suffix or '(без расширения)'}")
    if suffix in EXCEL_SUFFIXES:
        return list_excel_sheets(file_bytes)
    return [""]


def preview_linked_source(
    path: str | Path,
    sheet_name: str,
    header_row: int,
    mineral_key: str,
) -> pd.DataFrame:
    """Read and calculate a preview from a linked local source."""
    source = validate_source_path(path)
    df, _, _ = read_tabular_path(source, sheet_name or None, int(header_row))
    return _calculate_mineral(df, mineral_key)


def preview_uploaded_source(
    file_bytes: bytes,
    filename: str,
    sheet_name: str,
    header_row: int,
    mineral_key: str,
) -> pd.DataFrame:
    """Read and calculate a preview from uploaded bytes without storing them."""
    df, _, _ = read_tabular_with_map(file_bytes, filename, sheet_name or None, int(header_row))
    return _calculate_mineral(df, mineral_key)


def import_linked_sheets(
    *,
    project_id: int,
    path: str | Path,
    sheet_names: list[str],
    mineral_key: str,
    dataset_name: str,
    header_row: int,
) -> ImportBatchResult:
    """Import selected sheets while keeping a live link to the user's local source file."""
    source = validate_source_path(path)
    if not sheet_names:
        raise ValueError("Не выбран ни один лист для импорта")

    source_hash = sha256_file(source)
    dataset_ids: list[int] = []
    for sheet_name in sheet_names:
        df, column_map, source_rows = read_tabular_path(source, sheet_name or None, int(header_row))
        calculated = _calculate_mineral(df, mineral_key)
        name = _dataset_name(dataset_name, source.stem, sheet_name, len(sheet_names))
        dataset_ids.append(
            _save_dataset(
                project_id=project_id,
                df=calculated,
                dataset_name=name,
                mineral_key=mineral_key,
                source_filename=source.name,
                source_sheet=sheet_name or "",
                source_hash=source_hash,
                column_map=column_map,
                source_rows=source_rows,
                source_path=str(source),
                source_kind="linked",
                header_row=int(header_row),
                sync_enabled=source.suffix.lower() in SYNCABLE_SUFFIXES,
            )
        )
    return ImportBatchResult(tuple(dataset_ids), source)


def import_uploaded_sheets(
    *,
    project_id: int,
    file_bytes: bytes,
    filename: str,
    sheet_names: list[str],
    mineral_key: str,
    dataset_name: str,
    header_row: int,
) -> ImportBatchResult:
    """Store an uploaded source as a managed copy and import selected sheets from it."""
    if not sheet_names:
        raise ValueError("Не выбран ни один лист для импорта")
    list_uploaded_sheets(file_bytes, filename)  # validates the filename and workbook readability

    managed_path = _store_managed_source(project_id, filename, file_bytes)
    source_hash = sha256_bytes(file_bytes)
    dataset_ids: list[int] = []
    for sheet_name in sheet_names:
        df, column_map, source_rows = read_tabular_with_map(
            file_bytes,
            filename,
            sheet_name or None,
            int(header_row),
        )
        calculated = _calculate_mineral(df, mineral_key)
        name = _dataset_name(dataset_name, Path(filename).stem, sheet_name, len(sheet_names))
        dataset_ids.append(
            _save_dataset(
                project_id=project_id,
                df=calculated,
                dataset_name=name,
                mineral_key=mineral_key,
                source_filename=Path(filename).name,
                source_sheet=sheet_name or "",
                source_hash=source_hash,
                column_map=column_map,
                source_rows=source_rows,
                source_path=str(managed_path),
                source_kind="managed_copy",
                header_row=int(header_row),
                sync_enabled=managed_path.suffix.lower() in SYNCABLE_SUFFIXES,
            )
        )
    return ImportBatchResult(tuple(dataset_ids), managed_path)


def refresh_dataset_from_source(dataset_id: int) -> int:
    """Reload a linked dataset, recalculate its mineral data, and preserve point IDs by Excel row."""
    dataset = get_dataset(int(dataset_id))
    df, column_map, source_rows, new_hash = reload_linked_source(int(dataset_id))
    calculated = _calculate_mineral(df, dataset.get("mineral_key") or "generic")
    replace_dataset_rows(
        int(dataset_id),
        calculated,
        source_rows=source_rows,
        preserve_ids_by_source_row=True,
    )
    update_dataset_metadata(
        int(dataset_id),
        source_sha256=new_hash,
        column_map_json=column_map,
        row_count=len(calculated),
    )
    return len(calculated)


def _calculate_mineral(df: pd.DataFrame, mineral_key: str) -> pd.DataFrame:
    mineral = MINERALS.get(mineral_key)
    if mineral is None:
        raise KeyError(f"Неизвестный минерал: {mineral_key}")
    return mineral.calculate(df)


def _dataset_name(base_name: str, fallback: str, sheet_name: str, sheet_count: int) -> str:
    name = base_name.strip() or fallback
    return f"{name} · {sheet_name}" if sheet_count > 1 and sheet_name else name


def _store_managed_source(project_id: int, filename: str, data: bytes) -> Path:
    source_dir = DATA_DIR / f"project_{int(project_id)}" / "managed_sources"
    source_dir.mkdir(parents=True, exist_ok=True)
    clean_name = Path(filename).name
    if not clean_name:
        raise ValueError("Имя загруженного файла пустое")
    target = source_dir / f"{uuid4().hex[:10]}_{clean_name}"
    target.write_bytes(data)
    return target.resolve()


def _save_dataset(
    *,
    project_id: int,
    df: pd.DataFrame,
    dataset_name: str,
    mineral_key: str,
    source_filename: str,
    source_sheet: str,
    source_hash: str,
    column_map: dict,
    source_rows: list[int],
    source_path: str,
    source_kind: str,
    header_row: int,
    sync_enabled: bool,
) -> int:
    project_dir = DATA_DIR / f"project_{int(project_id)}"
    project_dir.mkdir(parents=True, exist_ok=True)
    csv_path = project_dir / f"dataset_{uuid4().hex}.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    dataset_id = add_dataset(
        project_id=int(project_id),
        name=dataset_name,
        mineral_key=mineral_key,
        source_filename=source_filename,
        source_sheet=source_sheet,
        source_sha256=source_hash,
        csv_path=str(csv_path),
        row_count=len(df),
        source_path=source_path,
        source_kind=source_kind,
        header_row=int(header_row),
        column_map=column_map,
        sync_enabled=bool(sync_enabled),
    )
    replace_dataset_rows(dataset_id, df, source_rows=source_rows)
    return dataset_id
