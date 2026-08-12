from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from uuid import uuid4

import pandas as pd

from petrolab.column_schema import (
    SheetSchema,
    apply_semantic_mapping,
    inspect_sheet_schema,
    resolve_semantic_mapping,
    stored_semantic_mapping,
)
from petrolab.db import DATA_DIR, add_dataset, get_dataset, replace_dataset_rows, update_dataset_metadata
from petrolab.io_utils import (
    list_excel_sheets,
    list_excel_sheets_path,
    read_tabular_path,
    read_tabular_with_map,
    sha256_bytes,
    sha256_file,
)
from petrolab.minerals.registry import MINERALS
from petrolab.repositories.analysis_refresh_repository import (
    RefreshPersistenceResult,
    replace_dataset_rows_stable,
)
from petrolab.sources import reload_linked_source

SUPPORTED_SOURCE_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".csv"}
EXCEL_SUFFIXES = {".xlsx", ".xlsm", ".xls"}
SYNCABLE_SUFFIXES = {".xlsx", ".xlsm"}


@dataclass(frozen=True)
class ImportBatchResult:
    dataset_ids: tuple[int, ...]
    source_path: Path

    @property
    def count(self) -> int:
        return len(self.dataset_ids)


@dataclass(frozen=True)
class ImportSchemaPreview:
    sheet_name: str
    schema: SheetSchema
    source_headers: tuple[tuple[str, str], ...]
    duplicate_canonical_columns: tuple[str, ...]
    measurement_notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class RefreshResult:
    dataset_id: int
    row_count: int
    reused_count: int
    new_count: int
    removed_count: int
    moved_rows_detected: bool
    recovered_roles: tuple[str, ...] = ()
    detached_image_count: int = 0
    positional_reused_count: int = 0


def validate_source_path(path: str | Path) -> Path:
    source = Path(path).expanduser()
    if not source.exists():
        raise FileNotFoundError(source)
    if not source.is_file():
        raise ValueError(f"Источник не является файлом: {source}")
    if source.suffix.lower() not in SUPPORTED_SOURCE_SUFFIXES:
        supported = ", ".join(sorted(SUPPORTED_SOURCE_SUFFIXES))
        raise ValueError(
            f"Неподдерживаемый формат {source.suffix or '(без расширения)'}. Поддерживаются: {supported}"
        )
    return source.resolve()


def list_linked_sheets(path: str | Path) -> list[str]:
    source = validate_source_path(path)
    if source.suffix.lower() in EXCEL_SUFFIXES:
        return list_excel_sheets_path(source)
    return [""]


def list_uploaded_sheets(file_bytes: bytes, filename: str) -> list[str]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SOURCE_SUFFIXES:
        raise ValueError(f"Неподдерживаемый формат: {suffix or '(без расширения)'}")
    if suffix in EXCEL_SUFFIXES:
        return list_excel_sheets(file_bytes)
    return [""]


def inspect_linked_sheet(path: str | Path, sheet_name: str, header_row: int) -> ImportSchemaPreview:
    source = validate_source_path(path)
    dataframe, column_map, _ = read_tabular_path(source, sheet_name or None, int(header_row))
    return _schema_preview(sheet_name, dataframe, column_map)


def inspect_uploaded_sheet(
    file_bytes: bytes,
    filename: str,
    sheet_name: str,
    header_row: int,
) -> ImportSchemaPreview:
    dataframe, column_map, _ = read_tabular_with_map(file_bytes, filename, sheet_name or None, int(header_row))
    return _schema_preview(sheet_name, dataframe, column_map)


def preview_linked_source(
    path: str | Path,
    sheet_name: str,
    header_row: int,
    mineral_key: str,
    semantic_map: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    source = validate_source_path(path)
    dataframe, column_map, _ = read_tabular_path(source, sheet_name or None, int(header_row))
    mapped, _, _ = apply_semantic_mapping(dataframe, column_map, semantic_map)
    return _calculate_mineral(mapped, mineral_key)


def preview_uploaded_source(
    file_bytes: bytes,
    filename: str,
    sheet_name: str,
    header_row: int,
    mineral_key: str,
    semantic_map: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    dataframe, column_map, _ = read_tabular_with_map(file_bytes, filename, sheet_name or None, int(header_row))
    mapped, _, _ = apply_semantic_mapping(dataframe, column_map, semantic_map)
    return _calculate_mineral(mapped, mineral_key)


def import_linked_sheets(
    *,
    project_id: int,
    path: str | Path,
    sheet_names: list[str],
    mineral_key: str,
    dataset_name: str,
    header_row: int,
    semantic_maps: Mapping[str, Mapping[str, str]] | None = None,
) -> ImportBatchResult:
    source = validate_source_path(path)
    if not sheet_names:
        raise ValueError("Не выбран ни один лист для импорта")

    source_hash = sha256_file(source)
    dataset_ids: list[int] = []
    for sheet_name in sheet_names:
        dataframe, column_map, source_rows = read_tabular_path(source, sheet_name or None, int(header_row))
        mapped, mapped_column_map, _ = apply_semantic_mapping(
            dataframe, column_map, (semantic_maps or {}).get(sheet_name, {})
        )
        calculated = _calculate_mineral(mapped, mineral_key)
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
                column_map=mapped_column_map,
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
    semantic_maps: Mapping[str, Mapping[str, str]] | None = None,
) -> ImportBatchResult:
    if not sheet_names:
        raise ValueError("Не выбран ни один лист для импорта")
    list_uploaded_sheets(file_bytes, filename)

    managed_path = _store_managed_source(project_id, filename, file_bytes)
    source_hash = sha256_bytes(file_bytes)
    dataset_ids: list[int] = []
    for sheet_name in sheet_names:
        dataframe, column_map, source_rows = read_tabular_with_map(
            file_bytes, filename, sheet_name or None, int(header_row)
        )
        mapped, mapped_column_map, _ = apply_semantic_mapping(
            dataframe, column_map, (semantic_maps or {}).get(sheet_name, {})
        )
        calculated = _calculate_mineral(mapped, mineral_key)
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
                column_map=mapped_column_map,
                source_rows=source_rows,
                source_path=str(managed_path),
                source_kind="managed_copy",
                header_row=int(header_row),
                sync_enabled=managed_path.suffix.lower() in SYNCABLE_SUFFIXES,
            )
        )
    return ImportBatchResult(tuple(dataset_ids), managed_path)


def refresh_dataset_from_source(dataset_id: int) -> RefreshResult:
    """Reload a source while preserving identities across edits, inserts and sorting."""
    dataset = get_dataset(int(dataset_id))
    dataframe, column_map, source_rows, new_hash = reload_linked_source(int(dataset_id))
    stored_map = json.loads(dataset.get("column_map_json") or "{}")
    previous_semantic = stored_semantic_mapping(stored_map)
    semantic_map = resolve_semantic_mapping(dataframe.columns, previous_semantic)
    recovered_roles = tuple(
        role for role, previous in previous_semantic.items()
        if role in semantic_map and semantic_map[role] != previous
    )

    mapped, mapped_column_map, _ = apply_semantic_mapping(dataframe, column_map, semantic_map)
    calculated = _calculate_mineral(mapped, dataset.get("mineral_key") or "generic")
    persistence: RefreshPersistenceResult = replace_dataset_rows_stable(
        int(dataset_id), calculated, source_rows
    )
    update_dataset_metadata(
        int(dataset_id),
        source_sha256=new_hash,
        column_map_json=mapped_column_map,
        row_count=len(calculated),
    )
    return RefreshResult(
        dataset_id=int(dataset_id),
        row_count=persistence.row_count,
        reused_count=persistence.reused_count,
        new_count=persistence.new_count,
        removed_count=persistence.removed_count,
        moved_rows_detected=persistence.moved_rows_detected,
        recovered_roles=recovered_roles,
        detached_image_count=persistence.detached_image_count,
        positional_reused_count=persistence.positional_reused_count,
    )


def _schema_preview(
    sheet_name: str,
    dataframe: pd.DataFrame,
    column_map: Mapping[str, Mapping[str, object]],
) -> ImportSchemaPreview:
    pairs: list[tuple[str, str]] = []
    duplicates: list[str] = []
    notes: list[str] = []
    for normalized in dataframe.columns:
        if str(normalized) in {"Σ оксидов", "QC суммы", "QC железа"}:
            continue
        info = column_map.get(str(normalized), {})
        original = str(info.get("original", normalized))
        pairs.append((original, str(normalized)))
        if "__" in str(normalized) and str(normalized).rsplit("__", 1)[-1].isdigit():
            duplicates.append(str(normalized))
        source_unit = str(info.get("source_unit") or "")
        canonical_unit = str(info.get("canonical_unit") or "")
        factor = float(info.get("to_canonical_factor", 1.0) or 1.0)
        warning = str(info.get("warning") or "")
        if source_unit and canonical_unit and (factor != 1.0 or source_unit != canonical_unit):
            notes.append(f"{original} → {normalized}: {source_unit} → {canonical_unit}, ×{factor:g}")
        if warning:
            notes.append(f"{original}: {warning}")
    return ImportSchemaPreview(
        sheet_name=sheet_name,
        schema=inspect_sheet_schema(dataframe.columns),
        source_headers=tuple(pairs),
        duplicate_canonical_columns=tuple(duplicates),
        measurement_notes=tuple(dict.fromkeys(notes)),
    )


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
