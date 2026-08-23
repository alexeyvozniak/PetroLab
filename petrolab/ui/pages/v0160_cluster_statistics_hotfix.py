from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import attach_work_groups
from petrolab.dataframe_utils import apply_quick_filter, dataset_label
from petrolab.dataset_visibility import visible_working_datasets
from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.generations import attach_generations
from petrolab.source_registry import attach_study_metadata
from petrolab.statistics import prepare_matrix, run_clustering
from petrolab.ui.cluster_plot_handoff import seed_cluster_plot_handoff
from petrolab.ui.project_context import active_project_id
from petrolab.ui.selection_context import read_row_states

from . import statistics as _stats
from . import v0160_statistics_integrity_hotfix as _integrity


def _selected_statistics_dataframe(project_id: int) -> pd.DataFrame:
    datasets = visible_working_datasets(list_accessible_datasets(int(project_id)))
    labels = {dataset_label(item): int(item["id"]) for item in datasets}
    selected_labels = st.session_state.get("statistics_datasets")
    if not isinstance(selected_labels, list):
        selected_labels = list(labels)
    dataset_ids = [labels[label] for label in selected_labels if label in labels]
    if not dataset_ids:
        return pd.DataFrame()
    dataframe = attach_study_metadata(
        attach_generations(
            attach_work_groups(load_unified_with_derived(int(project_id), dataset_ids))
        )
    )
    if dataframe.empty:
        return dataframe
    if "Минерал" in dataframe.columns:
        minerals = st.session_state.get("statistics_minerals")
        if isinstance(minerals, list) and minerals:
            dataframe = dataframe[dataframe["Минерал"].astype(str).isin(minerals)].copy()
    query = str(st.session_state.get("statistics_search") or "")
    dataframe = apply_quick_filter(dataframe, query)
    states = read_row_states()
    if states.excluded and "_analysis_id" in dataframe.columns:
        dataframe = dataframe.loc[
            ~dataframe["_analysis_id"].astype(str).isin(set(states.excluded))
        ].copy()
    return dataframe


def _cluster_columns_and_basis() -> tuple[list[str], str]:
    basis = str(st.session_state.get("stats_cluster_basis") or "clr")
    if basis == "clr":
        domain = str(st.session_state.get("stats_cluster_features_clr_domain") or "oxide_wt")
        raw = st.session_state.get(f"stats_cluster_features_clr_{domain}")
    else:
        raw = st.session_state.get("stats_cluster_features_euclidean")
    columns = [str(value) for value in raw or [] if str(value)]
    return columns, basis


def _current_cluster_overlay() -> tuple[list[int], list[str], dict[str, int]] | None:
    if str(st.session_state.get("statistics_section") or "PCA") != "Кластеры":
        return None
    if str(st.session_state.get("statistics_scope") or "Активный проект") != "Активный проект":
        return None
    project_id = active_project_id()
    if project_id is None:
        return None
    dataframe = _selected_statistics_dataframe(int(project_id))
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        return None
    columns, basis = _cluster_columns_and_basis()
    if len(columns) < 2 or any(column not in dataframe.columns for column in columns):
        return None
    scaler = "none" if basis == "clr" else str(st.session_state.get("stats_cluster_scaler") or "standard")
    try:
        prepared = prepare_matrix(
            dataframe,
            columns,
            scaler=scaler,
            impute="median",
            transform=basis,
        )
    except ValueError:
        return None
    if len(prepared.index) < 2:
        return None
    method = str(st.session_state.get("stats_cluster_method") or "kmeans")
    kwargs: dict[str, Any] = {"method": method}
    if method in {"kmeans", "hierarchical"}:
        kwargs["n_clusters"] = int(st.session_state.get("stats_cluster_n") or min(3, len(prepared.index)))
    elif method == "dbscan":
        kwargs["eps"] = float(st.session_state.get("stats_dbscan_eps") or 0.8)
        kwargs["min_samples"] = int(st.session_state.get("stats_dbscan_min_samples") or min(5, len(prepared.index)))
    elif method == "hdbscan":
        kwargs["min_cluster_size"] = int(st.session_state.get("stats_hdbscan_min_cluster") or min(5, len(prepared.index)))
        kwargs["min_samples"] = int(st.session_state.get("stats_hdbscan_min_samples") or min(5, len(prepared.index)))
    try:
        result = run_clustering(prepared, **kwargs)
    except ValueError:
        return None
    rows = dataframe.loc[result.labels.index].copy()
    ids = rows["_analysis_id"].astype(str).tolist()
    mapping = {
        analysis_id: int(cluster)
        for analysis_id, cluster in zip(ids, result.labels.astype(int).tolist())
    }
    dataset_ids: list[int] = []
    if "_dataset_id" in rows.columns:
        dataset_ids = list(dict.fromkeys(
            int(value)
            for value in pd.to_numeric(rows["_dataset_id"], errors="coerce").dropna().tolist()
        ))
    return dataset_ids, ids, mapping


def render_statistics_page() -> None:
    original_seed = _stats.seed_selection_plot_handoff
    original_button = st.button
    original_caption = st.caption

    def seed_with_clusters(state, *, dataset_ids, analysis_ids, origin="Selection"):
        overlay = _current_cluster_overlay()
        if overlay is None:
            return original_seed(
                state,
                dataset_ids=dataset_ids,
                analysis_ids=analysis_ids,
                origin=origin,
            )
        all_dataset_ids, all_analysis_ids, mapping = overlay
        return seed_cluster_plot_handoff(
            state,
            dataset_ids=all_dataset_ids,
            analysis_ids=all_analysis_ids,
            cluster_by_analysis_id=mapping,
        )

    def button(label, *args, **kwargs):
        if str(kwargs.get("key") or "") == "stats_cluster_to_xy":
            kwargs["disabled"] = False
            label = "Показать кластеры на XY"
            kwargs["help"] = (
                "Открыть все рассчитанные кластеры на обычной XY-диаграмме. "
                "Выбранные кластеры останутся Selection; Cluster не записывается как Generation."
            )
        return original_button(label, *args, **kwargs)

    def caption(body, *args, **kwargs):
        text = str(body)
        text = text.replace(
            "Строки с пропуском, нулём или отрицательным значением исключаются; PetroLab не подставляет псевдосчёт без DL.",
            "Отрицательные аналитические концентрации сначала принимаются равными 0 только в рабочем слое. "
            "Строки с нулём затем исключаются из CLR; псевдосчёт без DL не подставляется.",
        )
        text = text.replace(
            "CLR: исключено строк с пропуском/нулём/отрицательным компонентом:",
            "CLR: исключено строк с пропуском/нулём после обнуления отрицательных концентраций:",
        )
        return original_caption(text, *args, **kwargs)

    _stats.seed_selection_plot_handoff = seed_with_clusters
    st.button = button
    st.caption = caption
    try:
        _integrity.render_statistics_page()
    finally:
        _stats.seed_selection_plot_handoff = original_seed
        st.button = original_button
        st.caption = original_caption
