from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import attach_work_groups
from petrolab.dataframe_utils import apply_quick_filter
from petrolab.db import list_accessible_datasets, list_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.generations import attach_generations
from petrolab.sample_registry import list_samples
from petrolab.ui.layout import render_badges, render_work_context
from petrolab.ui.reference_selection import render_manual_selection_table, render_selection_action_bar
from petrolab.ui.selection_context import read_selection

from . import database_browser as _legacy


_FILTER_FIELDS = (
    ("Sample", ("Sample", "Образец")),
    ("Минерал", ("Минерал", "Mineral")),
    ("Generation", ("Generation", "Генерация")),
    ("Method", ("Method", "Метод", "Technique", "Метод анализа")),
)


def _first_column(dataframe: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    lowered = {str(column).casefold(): str(column) for column in dataframe.columns}
    for name in names:
        column = lowered.get(str(name).casefold())
        if column:
            return column
    return None


def _object_context(dataframe: pd.DataFrame, project_id: int, scope: str) -> pd.DataFrame:
    if scope != "Активный проект" or "Sample" not in dataframe.columns or "Object" in dataframe.columns:
        return dataframe
    object_by_sample = {
        str(row["name"]): str(row.get("locality") or "")
        for row in list_samples(project_id)
        if str(row.get("locality") or "").strip()
    }
    if not object_by_sample:
        return dataframe
    result = dataframe.copy()
    result["Object"] = result["Sample"].astype(str).map(object_by_sample).fillna("")
    return result


def _render_reference_selection(project_id: int, scope: str, query: str) -> None:
    datasets = list_accessible_datasets(project_id) if scope == "Активный проект" else list_datasets()
    dataset_ids = [int(dataset["id"]) for dataset in datasets]
    if not dataset_ids:
        return

    dataframe = attach_generations(attach_work_groups(load_unified_with_derived(None, dataset_ids)))
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        return
    dataframe = _object_context(dataframe, project_id, scope)
    dataframe = apply_quick_filter(dataframe, query)

    with st.container(border=True):
        top = st.columns([1.1, 1.1, 1.1, 1.1, 3.4])
        filtered = dataframe.copy()
        active_filters: list[str] = []
        for widget, (label, candidates) in zip(top[:4], _FILTER_FIELDS):
            column = _first_column(filtered, candidates)
            if column is None:
                widget.caption(f"{label}: нет поля")
                continue
            values = sorted(
                filtered[column].dropna().astype(str).loc[lambda value: value.str.strip().ne("")].unique()
            )
            selected = widget.multiselect(
                label,
                values,
                key=f"database_reference_{label}",
                placeholder="Все",
                label_visibility="collapsed",
            )
            if selected:
                filtered = filtered[filtered[column].astype(str).isin(selected)].copy()
                active_filters.append(f"{label}: {len(selected)}")

        context = read_selection()
        visible_ids = set(filtered["_analysis_id"].astype(str))
        top[4].markdown(f"**{len(filtered):,} анализов в текущем виде**".replace(",", " "))
        top[4].caption(
            "Фильтры меняют только вид. Галочки ниже создают одну общую рабочую выборку."
            + (" · " + " · ".join(active_filters) if active_filters else "")
        )
        render_work_context(
            area="активный проект · база" if scope == "Активный проект" else "все проекты · база",
            visible_count=len(filtered),
            selection_count=context.count,
            selection_visible_count=len(visible_ids & set(context.analysis_ids)),
            note="Selection не меняет Generation, QC и исходные значения",
        )

        display = [
            column
            for column in [
                "Object", "Sample", "Grain", "Point", "Минерал", "Generation",
                "Method", "QC уровень", "QC решение", "Набор", "Проект",
            ]
            if column in filtered.columns
        ]
        render_manual_selection_table(
            filtered,
            key_prefix="database_reference_table",
            origin="База · ручной отбор",
            columns=display,
            height=360,
            max_rows=3000,
        )
        render_badges([
            (f"{read_selection().count} выбрано", "accent"),
            (f"{len(dataset_ids)} наборов", "neutral"),
        ])
        render_selection_action_bar(
            filtered,
            key_prefix="database_reference_bottom",
            project_id=project_id if scope == "Активный проект" else None,
            show_images=True,
            show_statistics=True,
        )


def render_database_reference_page() -> None:
    """Keep the mature sample/database tools, but replace the old filter-only selection with the approved table selection UI."""
    original = _legacy._render_selection_toolbar
    _legacy._render_selection_toolbar = _render_reference_selection
    try:
        _legacy.render_database_browser_page()
    finally:
        _legacy._render_selection_toolbar = original
