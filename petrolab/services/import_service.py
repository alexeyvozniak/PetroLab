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
from petrolab.measurement_semantics import (
    apply_measurement_overrides,
    stored_measurement_overrides,
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
    recognized_oxides: tuple[tuple[str, str, str], ...] = ()
    recognized_traces: tuple[tuple[str, str, str], ...] = ()
    row_count: int = 0
    empty_cells: int = 0
    detection_limit_cells: int = 0
    import_sections: tuple[tuple[str, int], ...] = ()
    quality_counts: tuple[tuple[str, int], ...] = ()


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
    positional_fallback_disabled: bool = False


@dataclass(frozen=True)
class _PreparedSheet:
    sheet_name: str
    dataframe: pd.DataFrame
    column_map: dict
    source_rows: list[int]
    mineral_key: str
    header_row: int


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
        return _prioritize_analytical_sheets(source.read_bytes(), source.name, list_excel_sheets_path(source))
    return [""]


def list_uploaded_sheets(file_bytes: bytes, filename: str) -> list[str]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SOURCE_SUFFIXES:
        raise ValueError(f"Неподдерживаемый формат: {suffix or '(без расширения)'}")
    if suffix in EXCEL_SUFFIXES:
        return _prioritize_analytical_sheets(file_bytes, filename, list_excel_sheets(file_bytes))
    return [""]


def _prioritize_analytical_sheets(file_bytes: bytes, filename: str, sheet_names: list[str]) -> list[str]:
    """Put a detected multi-block EDS result sheet before its companion BSE map sheet."""
    eds: list[str] = []
    other: list[str] = []
    for sheet_name in sheet_names:
        try:
            _, column_map, _ = read_tabular_with_map(file_bytes, filename, sheet_name, 1)
            adapter = column_map.get("__schema__", {}).get("adapter")
        except Exception:
            adapter = None
        (eds if adapter == "eds_multiblock" else other).append(sheet_name)
    return eds + other


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
    measurement_map: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    source = validate_source_path(path)
    dataframe, column_map, _ = read_tabular_path(source, sheet_name or None, int(header_row))
    mapped, mapped_column_map, _ = apply_semantic_mapping(dataframe, column_map, semantic_map)
    mapped, _, _ = apply_measurement_overrides(mapped, mapped_column_map, measurement_map)
    return _calculate_mineral(mapped, mineral_key)


def preview_uploaded_source(
    file_bytes: bytes,
    filename: str,
    sheet_name: str,
    header_row: int,
    mineral_key: str,
    semantic_map: Mapping[str, str] | None = None,
    measurement_map: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    dataframe, column_map, _ = read_tabular_with_map(file_bytes, filename, sheet_name or None, int(header_row))
    mapped, mapped_column_map, _ = apply_semantic_mapping(dataframe, column_map, semantic_map)
    mapped, _, _ = apply_measurement_overrides(mapped, mapped_column_map, measurement_map)
    return _calculate_mineral(mapped, mineral_key)


def _prepare_sheet(
    dataframe: pd.DataFrame,
    column_map: dict,
    source_rows: list[int],
    *,
    sheet_name: str,
    mineral_key: str,
    header_row: int,
    semantic_map: Mapping[str, str] | None,
    measurement_map: Mapping[str, str] | None,
) -> _PreparedSheet:
    """Complete all fallible schema/calculation work before a dataset is persisted."""
    try:
        mapped, mapped_column_map, _ = apply_semantic_mapping(dataframe, column_map, semantic_map)
        mapped, mapped_column_map, _ = apply_measurement_overrides(
            mapped, mapped_column_map, measurement_map
        )
        calculated = _calculate_mineral(mapped, mineral_key)
    except Exception as exc:
        label = sheet_name or "CSV/активный лист"
        raise ValueError(f"Лист «{label}» не прошёл preflight импорта: {exc}") from exc
    return _PreparedSheet(
        sheet_name,
        calculated,
        mapped_column_map,
        source_rows,
        mineral_key,
        int(header_row),
    )


def _sheet_header_row(
    sheet_name: str,
    default: int,
    header_rows: Mapping[str, int] | None,
) -> int:
    value = (header_rows or {}).get(sheet_name, default)
    result = int(value)
    if result < 1:
        raise ValueError(f"Лист «{sheet_name or 'CSV'}»: строка заголовков должна быть >= 1")
    return result


def _sheet_mineral_key(
    sheet_name: str,
    default: str,
    mineral_keys: Mapping[str, str] | None,
) -> str:
    value = str((mineral_keys or {}).get(sheet_name, default))
    if value not in MINERALS:
        raise KeyError(f"Лист «{sheet_name or 'CSV'}»: неизвестный минерал {value}")
    return value


def _prepare_linked_batch(
    source: Path,
    sheet_names: list[str],
    *,
    header_row: int,
    mineral_key: str,
    header_rows: Mapping[str, int] | None,
    mineral_keys: Mapping[str, str] | None,
    semantic_maps: Mapping[str, Mapping[str, str]] | None,
    measurement_maps: Mapping[str, Mapping[str, str]] | None,
) -> list[_PreparedSheet]:
    prepared: list[_PreparedSheet] = []
    for sheet_name in sheet_names:
        current_header = _sheet_header_row(sheet_name, header_row, header_rows)
        current_mineral = _sheet_mineral_key(sheet_name, mineral_key, mineral_keys)
        dataframe, column_map, source_rows = read_tabular_path(
            source, sheet_name or None, current_header
        )
        prepared.append(
            _prepare_sheet(
                dataframe,
                column_map,
                source_rows,
                sheet_name=sheet_name,
                mineral_key=current_mineral,
                header_row=current_header,
                semantic_map=(semantic_maps or {}).get(sheet_name, {}),
                measurement_map=(measurement_maps or {}).get(sheet_name, {}),
            )
        )
    return prepared


def _prepare_uploaded_batch(
    file_bytes: bytes,
    filename: str,
    sheet_names: list[str],
    *,
    header_row: int,
    mineral_key: str,
    header_rows: Mapping[str, int] | None,
    mineral_keys: Mapping[str, str] | None,
    semantic_maps: Mapping[str, Mapping[str, str]] | None,
    measurement_maps: Mapping[str, Mapping[str, str]] | None,
) -> list[_PreparedSheet]:
    prepared: list[_PreparedSheet] = []
    for sheet_name in sheet_names:
        current_header = _sheet_header_row(sheet_name, header_row, header_rows)
        current_mineral = _sheet_mineral_key(sheet_name, mineral_key, mineral_keys)
        dataframe, column_map, source_rows = read_tabular_with_map(
            file_bytes, filename, sheet_name or None, current_header
        )
        prepared.append(
            _prepare_sheet(
                dataframe,
                column_map,
                source_rows,
                sheet_name=sheet_name,
                mineral_key=current_mineral,
                header_row=current_header,
                semantic_map=(semantic_maps or {}).get(sheet_name, {}),
                measurement_map=(measurement_maps or {}).get(sheet_name, {}),
            )
        )
    return prepared


def import_linked_sheets(
    *,
    project_id: int,
    path: str | Path,
    sheet_names: list[str],
    mineral_key: str,
    dataset_name: str,
    header_row: int,
    semantic_maps: Mapping[str, Mapping[str, str]] | None = None,
    measurement_maps: Mapping[str, Mapping[str, str]] | None = None,
    header_rows: Mapping[str, int] | None = None,
    mineral_keys: Mapping[str, str] | None = None,
) -> ImportBatchResult:
    source = validate_source_path(path)
    if not sheet_names:
        raise ValueError("Не выбран ни один лист для импорта")

    # Preflight the entire workbook first. A schema/calculation failure on a later sheet
    # must not leave the earlier sheets partially imported into the project.
    prepared = _prepare_linked_batch(
        source,
        sheet_names,
        header_row=int(header_row),
        mineral_key=mineral_key,
        header_rows=header_rows,
        mineral_keys=mineral_keys,
        semantic_maps=semantic_maps,
        measurement_maps=measurement_maps,
    )
    source_hash = sha256_file(source)
    dataset_ids: list[int] = []
    for item in prepared:
        name = _dataset_name(dataset_name, source.stem, item.sheet_name, len(prepared))
        dataset_ids.append(
            _save_dataset(
                project_id=project_id,
                df=item.dataframe,
                dataset_name=name,
                mineral_key=item.mineral_key,
                source_filename=source.name,
                source_sheet=item.sheet_name or "",
                source_hash=source_hash,
                column_map=item.column_map,
                source_rows=item.source_rows,
                source_path=str(source),
                source_kind="linked",
                header_row=item.header_row,
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
    measurement_maps: Mapping[str, Mapping[str, str]] | None = None,
    header_rows: Mapping[str, int] | None = None,
    mineral_keys: Mapping[str, str] | None = None,
) -> ImportBatchResult:
    if not sheet_names:
        raise ValueError("Не выбран ни один лист для импорта")
    list_uploaded_sheets(file_bytes, filename)

    # Validate every selected sheet before writing the managed source or creating any
    # dataset rows. This keeps a failed multi-sheet import free of partial DB/file state.
    prepared = _prepare_uploaded_batch(
        file_bytes,
        filename,
        sheet_names,
        header_row=int(header_row),
        mineral_key=mineral_key,
        header_rows=header_rows,
        mineral_keys=mineral_keys,
        semantic_maps=semantic_maps,
        measurement_maps=measurement_maps,
    )
    managed_path = _store_managed_source(project_id, filename, file_bytes)
    source_hash = sha256_bytes(file_bytes)
    dataset_ids: list[int] = []
    for item in prepared:
        name = _dataset_name(dataset_name, Path(filename).stem, item.sheet_name, len(prepared))
        dataset_ids.append(
            _save_dataset(
                project_id=project_id,
                df=item.dataframe,
                dataset_name=name,
                mineral_key=item.mineral_key,
                source_filename=Path(filename).name,
                source_sheet=item.sheet_name or "",
                source_hash=source_hash,
                column_map=item.column_map,
                source_rows=item.source_rows,
                source_path=str(managed_path),
                source_kind="managed_copy",
                header_row=item.header_row,
                sync_enabled=managed_path.suffix.lower() in SYNCABLE_SUFFIXES,
            )
        )
    return ImportBatchResult(tuple(dataset_ids), managed_path)


def refresh_dataset_from_source(dataset_id: int) -> RefreshResult:
    """Reload a source while preserving identities and confirmed column semantics."""
    dataset = get_dataset(int(dataset_id))
    dataframe, column_map, source_rows, new_hash = reload_linked_source(int(dataset_id))
    stored_map = json.loads(dataset.get("column_map_json") or "{}")
    previous_semantic = stored_semantic_mapping(stored_map)
    measurement_map = stored_measurement_overrides(stored_map)
    semantic_map = resolve_semantic_mapping(dataframe.columns, previous_semantic)
    recovered_roles = tuple(
        role for role, previous in previous_semantic.items()
        if role in semantic_map and semantic_map[role] != previous
    )

    mapped, mapped_column_map, _ = apply_semantic_mapping(dataframe, column_map, semantic_map)
    mapped, mapped_column_map, _ = apply_measurement_overrides(
        mapped, mapped_column_map, measurement_map
    )
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
        positional_fallback_disabled=persistence.positional_fallback_disabled,
    )


def _schema_preview(
    sheet_name: str,
    dataframe: pd.DataFrame,
    column_map: Mapping[str, Mapping[str, object]],
) -> ImportSchemaPreview:
    pairs: list[tuple[str, str]] = []
    duplicates: list[str] = []
    notes: list[str] = []
    oxides: list[tuple[str, str, str]] = []
    traces: list[tuple[str, str, str]] = []
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
        kind = str(info.get("quantity_kind") or "")
        if kind == "oxide":
            oxides.append((original, str(normalized), canonical_unit or source_unit or "wt%"))
        elif kind in {"trace_element", "element_concentration", "element_unknown_unit"}:
            traces.append((original, str(normalized), canonical_unit or source_unit or "не указана"))
        factor = float(info.get("to_canonical_factor", 1.0) or 1.0)
        warning = str(info.get("warning") or "")
        if source_unit and canonical_unit and (factor != 1.0 or source_unit != canonical_unit):
            notes.append(f"{original} → {normalized}: {source_unit} → {canonical_unit}, ×{factor:g}")
        if warning:
            notes.append(f"{original}: {warning}")
    if "FeO" in dataframe.columns:
        notes.append(
            "FeO: подтвердите смысл колонки — отдельное Fe²⁺ или ΣFe, выраженное как FeO total."
        )
    if "Fe2O3" in dataframe.columns:
        notes.append(
            "Fe2O3: подтвердите смысл колонки — отдельно заданное Fe³⁺ или ΣFe, выраженное как Fe2O3 total."
        )
    detection_limits = [
        f"{info.get('original', normalized)}: {float(info['detection_limit']):g} {info.get('detection_limit_unit', '')}".strip()
        for normalized, info in column_map.items()
        if info.get("detection_limit") is not None
    ]
    if detection_limits:
        notes.append("D.L. 3σ сохранены для колонок: " + "; ".join(detection_limits))
    source_view = dataframe.astype("string")
    detection_limit_cells = int(source_view.apply(
        lambda column: column.str.strip().str.match(r"^(?:<|≤)\s*(?:DL|LOD|LOQ|[0-9])", case=False, na=False)
    ).to_numpy().sum())
    sections: tuple[tuple[str, int], ...] = ()
    if "Import section" in dataframe.columns:
        counts = dataframe["Import section"].fillna("без названия").astype(str).value_counts()
        sections = tuple((str(name), int(count)) for name, count in counts.items())
    quality_counts: tuple[tuple[str, int], ...] = ()
    if "QC уровень" in dataframe.columns:
        counts = dataframe["QC уровень"].fillna("не оценено").astype(str).value_counts()
        quality_counts = tuple((str(name), int(count)) for name, count in counts.items())
    return ImportSchemaPreview(
        sheet_name=sheet_name,
        schema=inspect_sheet_schema(dataframe.columns),
        source_headers=tuple(pairs),
        duplicate_canonical_columns=tuple(duplicates),
        measurement_notes=tuple(dict.fromkeys(notes)),
        recognized_oxides=tuple(oxides),
        recognized_traces=tuple(traces),
        row_count=int(len(dataframe)),
        empty_cells=int(dataframe.isna().to_numpy().sum()),
        detection_limit_cells=detection_limit_cells,
        import_sections=sections,
        quality_counts=quality_counts,
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
