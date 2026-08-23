from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from petrolab.analytical_sessions import annotation_table
from petrolab.db import list_accessible_datasets, load_dataset_dataframe


CONFIRMED_PHASE_COLUMN = "Подтверждённая фаза"
SOURCE_SHEET_DATASET_COLUMN = "Фазовый набор"


@dataclass(frozen=True)
class SourceSheetScope:
    key: str
    anchor_dataset_id: int
    dataset_ids: tuple[int, ...]
    source_filename: str
    source_sheet: str
    source_sha256: str
    row_count: int

    @property
    def label(self) -> str:
        sheet = self.source_sheet or "CSV"
        source = self.source_filename or "источник"
        return f"{sheet} · {self.row_count} анализов · {source}"


def _source_signature(dataset: dict) -> tuple[str, str, str]:
    return (
        str(dataset.get("source_sha256") or "").strip(),
        str(dataset.get("source_filename") or "").strip(),
        str(dataset.get("source_sheet") or "").strip(),
    )


def source_sheet_key(dataset: dict) -> str:
    sha, filename, sheet = _source_signature(dataset)
    stable = sha or filename
    return f"{stable}::{sheet or 'CSV'}"


def _phase_label_from_dataset(dataset: dict) -> str:
    name = str(dataset.get("name") or "").strip()
    mineral_key = str(dataset.get("mineral_key") or "").strip()
    if " · " in name and mineral_key and mineral_key != "generic":
        return name.rsplit(" · ", 1)[-1].strip()
    return mineral_key if mineral_key and mineral_key != "generic" else ""


def list_source_sheet_scopes(project_id: int, datasets: Iterable[dict] | None = None) -> list[SourceSheetScope]:
    rows = list(datasets) if datasets is not None else list_accessible_datasets(int(project_id))
    grouped: dict[str, list[dict]] = {}
    for dataset in rows:
        key = source_sheet_key(dataset)
        grouped.setdefault(key, []).append(dataset)

    scopes: list[SourceSheetScope] = []
    for key, members in grouped.items():
        ordered = sorted(members, key=lambda item: int(item["id"]))
        ids = tuple(int(item["id"]) for item in ordered)
        analysis_ids: set[str] = set()
        for dataset_id in ids:
            frame = load_dataset_dataframe(dataset_id, include_meta=True)
            if "_analysis_id" in frame.columns:
                analysis_ids.update(frame["_analysis_id"].astype(str).tolist())
        first = ordered[0]
        scopes.append(
            SourceSheetScope(
                key=key,
                anchor_dataset_id=ids[0],
                dataset_ids=ids,
                source_filename=str(first.get("source_filename") or ""),
                source_sheet=str(first.get("source_sheet") or ""),
                source_sha256=str(first.get("source_sha256") or ""),
                row_count=len(analysis_ids),
            )
        )
    return sorted(scopes, key=lambda item: (item.source_filename.casefold(), item.source_sheet.casefold(), item.key))


def source_sheet_scope_for_dataset(project_id: int, dataset_id: int) -> SourceSheetScope | None:
    target = int(dataset_id)
    for scope in list_source_sheet_scopes(int(project_id)):
        if target in scope.dataset_ids:
            return scope
    return None


def load_source_sheet_universe(project_id: int, scope: SourceSheetScope | int) -> pd.DataFrame:
    resolved = (
        source_sheet_scope_for_dataset(int(project_id), int(scope))
        if isinstance(scope, int)
        else scope
    )
    if resolved is None:
        return pd.DataFrame()

    datasets = {int(item["id"]): item for item in list_accessible_datasets(int(project_id))}
    frames: list[pd.DataFrame] = []
    for dataset_id in resolved.dataset_ids:
        dataset = datasets.get(int(dataset_id))
        if dataset is None:
            continue
        frame = load_dataset_dataframe(int(dataset_id), include_meta=True).copy()
        if frame.empty:
            continue
        frame[SOURCE_SHEET_DATASET_COLUMN] = str(dataset.get("name") or dataset_id)
        frame["_source_sheet_anchor_dataset_id"] = int(resolved.anchor_dataset_id)
        frames.append(frame)
    if not frames:
        return pd.DataFrame()

    out = pd.concat(frames, ignore_index=True, sort=False)
    if "_analysis_id" not in out.columns:
        return out
    out["_analysis_id"] = out["_analysis_id"].astype(str)
    out = out.drop_duplicates(subset=["_analysis_id"], keep="first")

    annotations = annotation_table(out["_analysis_id"].tolist(), namespace="phase")
    confirmed = [
        str((annotations.get(analysis_id, {}) or {}).get("confirmed_phase") or "").strip()
        for analysis_id in out["_analysis_id"].tolist()
    ]
    fallback_by_dataset = {
        int(dataset_id): _phase_label_from_dataset(dataset)
        for dataset_id, dataset in datasets.items()
    }
    if "_dataset_id" in out.columns:
        fallback = [fallback_by_dataset.get(int(value), "") for value in out["_dataset_id"]]
    else:
        fallback = [""] * len(out)
    out[CONFIRMED_PHASE_COLUMN] = [manual or inferred for manual, inferred in zip(confirmed, fallback)]

    sort_columns = [column for column in ("_source_row", "Point", "_analysis_id") if column in out.columns]
    if sort_columns:
        out = out.sort_values(sort_columns, kind="stable", na_position="last")
    return out.reset_index(drop=True)


def dataset_ids_share_source_sheet(project_id: int, anchor_dataset_id: int, dataset_ids: Iterable[int]) -> bool:
    scope = source_sheet_scope_for_dataset(int(project_id), int(anchor_dataset_id))
    if scope is None:
        return False
    allowed = set(scope.dataset_ids)
    return all(int(value) in allowed for value in dataset_ids)
