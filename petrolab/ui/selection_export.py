from __future__ import annotations

from io import BytesIO
from typing import Iterable

import pandas as pd

from petrolab.analysis_groups import attach_work_groups
from petrolab.dataframe_utils import human_point_label
from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.generations import attach_generations
from petrolab.source_registry import attach_study_metadata


def _ids(values: Iterable[object]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def resolve_selection_dataframe(
    project_id: int | None,
    analysis_ids: Iterable[object],
    *,
    current_dataframe: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Resolve immutable Selection IDs against the whole accessible project scope.

    The current page dataframe is only a fallback. Filtering, Hide and Exclude
    therefore do not silently truncate a prepared export when project context is
    available.
    """
    wanted_order = _ids(analysis_ids)
    if not wanted_order:
        return pd.DataFrame()
    wanted = set(wanted_order)

    dataframe = pd.DataFrame()
    if project_id is not None:
        datasets = list_accessible_datasets(int(project_id))
        dataset_ids = [int(item["id"]) for item in datasets]
        if dataset_ids:
            dataframe = attach_study_metadata(
                attach_generations(
                    attach_work_groups(load_unified_with_derived(int(project_id), dataset_ids))
                )
            )

    if dataframe.empty and current_dataframe is not None:
        dataframe = current_dataframe.copy()
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        return dataframe.iloc[0:0].copy()

    selected = dataframe.loc[dataframe["_analysis_id"].astype(str).isin(wanted)].copy()
    if selected.empty:
        return selected
    order = {analysis_id: index for index, analysis_id in enumerate(wanted_order)}
    selected["_petrolab_export_order"] = selected["_analysis_id"].astype(str).map(order)
    selected = selected.sort_values("_petrolab_export_order", kind="stable").drop(columns=["_petrolab_export_order"])
    return selected


def public_selection_frame(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Return a human-facing export frame with no internal PetroLab columns."""
    if dataframe.empty:
        return dataframe.copy()
    result = dataframe.copy()
    point_labels = [human_point_label(row) for _, row in result.iterrows()]
    public = [column for column in result.columns if not str(column).startswith("_")]
    result = result[public].copy()
    if "Точка" in result.columns:
        result["Точка"] = point_labels
    else:
        result.insert(0, "Точка", point_labels)
    return result


def selection_xlsx_bytes(dataframe: pd.DataFrame) -> bytes:
    public = public_selection_frame(dataframe)
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        public.to_excel(writer, sheet_name="Selection", index=False)
    return buffer.getvalue()
