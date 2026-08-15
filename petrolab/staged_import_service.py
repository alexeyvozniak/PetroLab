from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import pandas as pd

from petrolab.db import DATA_DIR
from petrolab.io_utils import normalize_columns_with_map, sha256_bytes
from petrolab.services.import_service import _save_dataset


@dataclass(frozen=True)
class StagedImportResult:
    dataset_ids: tuple[int, ...]
    source_path: Path


def _managed_staged_source(project_id: int, filename: str, data: bytes) -> Path:
    directory = DATA_DIR / f"project_{int(project_id)}" / "staged_sources"
    directory.mkdir(parents=True, exist_ok=True)
    clean = Path(filename).name or "source.xlsx"
    target = directory / f"{uuid4().hex[:10]}_{clean}"
    target.write_bytes(data)
    return target.resolve()


def _frame_column_map(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Normalize any user-created scientific fields while preserving metadata columns."""
    normalized, mapping = normalize_columns_with_map(frame)
    return normalized, mapping


def import_staged_frames(
    *,
    project_id: int,
    file_bytes: bytes,
    filename: str,
    frames: dict[str, pd.DataFrame],
    dataset_name: str,
    mineral_key: str = "generic",
    header_rows: dict[str, int] | None = None,
) -> StagedImportResult:
    """Persist confirmed staging frames as non-syncing managed copies.

    The original workbook is retained for provenance, but staged structural edits
    (block fill, row exclusion, custom metadata) are intentionally not written back.
    """
    if not frames:
        raise ValueError("Нет подготовленных листов для импорта")
    managed_path = _managed_staged_source(int(project_id), filename, file_bytes)
    source_hash = sha256_bytes(file_bytes)
    dataset_ids: list[int] = []
    multiple = len(frames) > 1
    for sheet, raw_frame in frames.items():
        frame = raw_frame.copy().reset_index(drop=True)
        normalized, column_map = _frame_column_map(frame)
        name = str(dataset_name).strip() or Path(filename).stem
        if multiple:
            name = f"{name} · {sheet or 'CSV'}"
        # These source-row numbers are staging positions, not writable Excel row IDs.
        source_rows = list(range(1, len(normalized) + 1))
        dataset_ids.append(
            _save_dataset(
                project_id=int(project_id),
                df=normalized,
                dataset_name=name,
                mineral_key=mineral_key,
                source_filename=Path(filename).name,
                source_sheet=str(sheet or ""),
                source_hash=source_hash,
                column_map=column_map,
                source_rows=source_rows,
                source_path=str(managed_path),
                source_kind="staged_copy",
                header_row=int((header_rows or {}).get(sheet, 1)),
                sync_enabled=False,
            )
        )
    return StagedImportResult(tuple(dataset_ids), managed_path)
