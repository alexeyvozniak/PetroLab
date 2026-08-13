from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping
from uuid import uuid4

import pandas as pd

from petrolab.column_schema import apply_semantic_mapping
from petrolab.db import connect
from petrolab.io_utils import read_tabular_path, read_tabular_with_map, sha256_bytes, sha256_file
from petrolab.measurement_semantics import apply_measurement_overrides


@dataclass(frozen=True)
class _Prepared:
    sheet: str
    dataframe: pd.DataFrame
    column_map: dict
    source_rows: list[int]
    mineral_key: str
    header_row: int


def _sheet_value(sheet: str, default, overrides: Mapping | None):
    return (overrides or {}).get(sheet, default)


def _prepare(
    svc,
    *,
    reader,
    sheet_names: list[str],
    default_header: int,
    default_mineral: str,
    header_rows: Mapping[str, int] | None,
    mineral_keys: Mapping[str, str] | None,
    semantic_maps: Mapping[str, Mapping[str, str]] | None,
    measurement_maps: Mapping[str, Mapping[str, str]] | None,
) -> list[_Prepared]:
    prepared: list[_Prepared] = []
    for sheet in sheet_names:
        header = int(_sheet_value(sheet, default_header, header_rows))
        mineral = str(_sheet_value(sheet, default_mineral, mineral_keys))
        if header < 1:
            raise ValueError(f"Лист «{sheet or 'CSV'}»: строка заголовков должна быть >= 1")
        if mineral not in svc.MINERALS:
            raise ValueError(f"Лист «{sheet or 'CSV'}»: неизвестный минерал {mineral}")
        try:
            frame, column_map, source_rows = reader(sheet, header)
            frame, column_map, _ = apply_semantic_mapping(
                frame, column_map, (semantic_maps or {}).get(sheet, {})
            )
            frame, column_map, _ = apply_measurement_overrides(
                frame, column_map, (measurement_maps or {}).get(sheet, {})
            )
            frame = svc._calculate_mineral(frame, mineral)
        except Exception as exc:
            raise ValueError(f"Лист «{sheet or 'CSV'}» не прошёл preflight: {exc}") from exc
        prepared.append(_Prepared(sheet, frame, column_map, source_rows, mineral, header))
    return prepared


def _delete_dataset(dataset_id: int) -> None:
    with connect() as con:
        con.execute("DELETE FROM analysis_rows WHERE dataset_id=?", (int(dataset_id),))
        con.execute("DELETE FROM datasets WHERE id=?", (int(dataset_id),))
        con.commit()


def _persist_one(
    svc,
    *,
    project_id: int,
    item: _Prepared,
    dataset_name: str,
    source_filename: str,
    source_hash: str,
    source_path: str,
    source_kind: str,
    sync_enabled: bool,
) -> tuple[int, Path]:
    project_dir = svc.DATA_DIR / f"project_{int(project_id)}"
    project_dir.mkdir(parents=True, exist_ok=True)
    csv_path = project_dir / f"dataset_{uuid4().hex}.csv"
    dataset_id: int | None = None
    try:
        item.dataframe.to_csv(csv_path, index=False, encoding="utf-8-sig")
        dataset_id = svc.add_dataset(
            project_id=int(project_id),
            name=dataset_name,
            mineral_key=item.mineral_key,
            source_filename=source_filename,
            source_sheet=item.sheet or "",
            source_sha256=source_hash,
            csv_path=str(csv_path),
            row_count=len(item.dataframe),
            source_path=source_path,
            source_kind=source_kind,
            header_row=item.header_row,
            column_map=item.column_map,
            sync_enabled=sync_enabled,
        )
        svc.replace_dataset_rows(dataset_id, item.dataframe, source_rows=item.source_rows)
        return dataset_id, csv_path
    except Exception:
        if dataset_id is not None:
            _delete_dataset(dataset_id)
        csv_path.unlink(missing_ok=True)
        raise


def _rollback(created: list[tuple[int, Path]]) -> None:
    for dataset_id, csv_path in reversed(created):
        try:
            _delete_dataset(dataset_id)
        finally:
            csv_path.unlink(missing_ok=True)


def install() -> None:
    from petrolab.services import import_service as svc

    def import_linked_sheets(
        *, project_id: int, path, sheet_names: list[str], mineral_key: str,
        dataset_name: str, header_row: int,
        semantic_maps=None, measurement_maps=None,
        header_rows=None, mineral_keys=None,
    ):
        source = svc.validate_source_path(path)
        if not sheet_names:
            raise ValueError("Не выбран ни один лист для импорта")
        prepared = _prepare(
            svc,
            reader=lambda sheet, header: read_tabular_path(source, sheet or None, header),
            sheet_names=sheet_names,
            default_header=int(header_row),
            default_mineral=mineral_key,
            header_rows=header_rows,
            mineral_keys=mineral_keys,
            semantic_maps=semantic_maps,
            measurement_maps=measurement_maps,
        )
        source_hash = sha256_file(source)
        created: list[tuple[int, Path]] = []
        try:
            for item in prepared:
                name = svc._dataset_name(dataset_name, source.stem, item.sheet, len(prepared))
                created.append(_persist_one(
                    svc, project_id=project_id, item=item, dataset_name=name,
                    source_filename=source.name, source_hash=source_hash,
                    source_path=str(source), source_kind="linked",
                    sync_enabled=source.suffix.lower() in svc.SYNCABLE_SUFFIXES,
                ))
        except Exception:
            _rollback(created)
            raise
        return svc.ImportBatchResult(tuple(item[0] for item in created), source)

    def import_uploaded_sheets(
        *, project_id: int, file_bytes: bytes, filename: str,
        sheet_names: list[str], mineral_key: str, dataset_name: str,
        header_row: int, semantic_maps=None, measurement_maps=None,
        header_rows=None, mineral_keys=None,
    ):
        if not sheet_names:
            raise ValueError("Не выбран ни один лист для импорта")
        svc.list_uploaded_sheets(file_bytes, filename)
        prepared = _prepare(
            svc,
            reader=lambda sheet, header: read_tabular_with_map(
                file_bytes, filename, sheet or None, header
            ),
            sheet_names=sheet_names,
            default_header=int(header_row),
            default_mineral=mineral_key,
            header_rows=header_rows,
            mineral_keys=mineral_keys,
            semantic_maps=semantic_maps,
            measurement_maps=measurement_maps,
        )
        managed_path = svc._store_managed_source(project_id, filename, file_bytes)
        source_hash = sha256_bytes(file_bytes)
        created: list[tuple[int, Path]] = []
        try:
            for item in prepared:
                name = svc._dataset_name(dataset_name, Path(filename).stem, item.sheet, len(prepared))
                created.append(_persist_one(
                    svc, project_id=project_id, item=item, dataset_name=name,
                    source_filename=Path(filename).name, source_hash=source_hash,
                    source_path=str(managed_path), source_kind="managed_copy",
                    # A browser upload is an internal PetroLab working copy, not the
                    # user's original workbook. Never expose it as a bidirectional target.
                    sync_enabled=False,
                ))
        except Exception:
            _rollback(created)
            managed_path.unlink(missing_ok=True)
            raise
        return svc.ImportBatchResult(tuple(item[0] for item in created), managed_path)

    svc.import_linked_sheets = import_linked_sheets
    svc.import_uploaded_sheets = import_uploaded_sheets

    from petrolab.recovery_runtime import install as install_recovery
    install_recovery()
