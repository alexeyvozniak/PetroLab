from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import attach_work_groups
from petrolab.dataframe_utils import apply_quick_filter, dataset_label
from petrolab.dataset_visibility import visible_working_datasets
from petrolab.db import list_accessible_datasets, list_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.generations import attach_generations
from petrolab.minerals.registry import MINERALS
from petrolab.source_registry import attach_study_metadata
from petrolab.ui.components import render_project_selector
from petrolab.ui.project_context import active_project_id


@dataclass(frozen=True)
class AnalysisScope:
    dataframe: pd.DataFrame
    project_id: int | None
    dataset_ids: tuple[int, ...]
    mineral_keys: tuple[str, ...]


def render_analysis_scope(
    key_prefix: str,
    *,
    allow_all_projects: bool = True,
    show_search: bool = True,
) -> AnalysisScope | None:
    project_id: int | None = None
    if allow_all_projects:
        scope = st.segmented_control(
            "Область данных",
            ["Активный проект", "Все проекты"],
            default="Активный проект",
            key=f"{key_prefix}_scope",
        )
    else:
        scope = "Активный проект"

    if scope == "Активный проект":
        project_id = active_project_id()
        if project_id is None:
            project = render_project_selector(f"{key_prefix}_project")
            if project is None:
                return None
            project_id = int(project["id"])

    raw_datasets = list_datasets(None) if scope == "Все проекты" else list_accessible_datasets(int(project_id))
    datasets = visible_working_datasets(raw_datasets)
    if not datasets:
        st.info("В выбранной области пока нет рабочих наборов анализов.")
        return None

    labels = {dataset_label(dataset): int(dataset["id"]) for dataset in datasets}
    pending_raw = st.session_state.pop(f"{key_prefix}_dataset_ids_pending", [])
    pending: set[int] = set()
    for value in pending_raw or []:
        try:
            pending.add(int(value))
        except (TypeError, ValueError):
            continue
    defaults = [label for label, dataset_id in labels.items() if dataset_id in pending] if pending else list(labels)
    if pending:
        st.session_state.pop(f"{key_prefix}_datasets", None)
    selected_labels = st.multiselect(
        "Наборы данных",
        list(labels),
        default=defaults,
        key=f"{key_prefix}_datasets",
    )
    dataset_ids = tuple(labels[label] for label in selected_labels)
    if not dataset_ids:
        st.info("Выберите хотя бы один набор данных.")
        return None

    dataframe = attach_study_metadata(
        attach_generations(
            attach_work_groups(load_unified_with_derived(project_id, list(dataset_ids)))
        )
    )
    if dataframe.empty:
        st.info("В выбранных наборах нет аналитических строк.")
        return None

    mineral_keys: tuple[str, ...] = ()
    if "Минерал" in dataframe.columns:
        available = sorted(dataframe["Минерал"].dropna().astype(str).unique())
        selected = st.multiselect(
            "Минералы",
            available,
            default=available,
            format_func=lambda key: MINERALS.get(key, MINERALS["generic"]).name_ru,
            key=f"{key_prefix}_minerals",
        )
        if not selected:
            st.info("Выберите хотя бы один минерал.")
            return None
        mineral_keys = tuple(selected)
        dataframe = dataframe[dataframe["Минерал"].astype(str).isin(selected)]

    if show_search:
        query = st.text_input("Поиск в выбранных данных", key=f"{key_prefix}_search")
        dataframe = apply_quick_filter(dataframe, query)

    if dataframe.empty:
        st.warning("После фильтрации не осталось строк.")
        return None
    return AnalysisScope(dataframe.copy(), project_id, dataset_ids, mineral_keys)
