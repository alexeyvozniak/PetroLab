"""Переходы из химической разметки к кластеризации и сравнению."""
from __future__ import annotations

import streamlit as st

from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_accessible_datasets
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project_id
from petrolab.ui.workflow_continuity_v0154 import render_plots_page_v0154 as _render_base_plots


def _current_chemical_dataset_ids() -> list[int]:
    """Вернуть наборы текущей химической работы, не подмешивая чужие данные проекта."""
    recipe = st.session_state.get("loaded_recipe") or {}
    raw = recipe.get("dataset_ids") if isinstance(recipe, dict) else None
    if not raw:
        raw = st.session_state.get("workflow_plot_dataset_ids", []) or []
    result: list[int] = []
    for value in raw or []:
        try:
            dataset_id = int(value)
        except (TypeError, ValueError):
            continue
        if dataset_id not in result:
            result.append(dataset_id)
    return result


def _prepare_statistics_scope(dataset_ids: list[int]) -> None:
    """Передать в статистику ровно текущие наборы, чтобы кластеризация не начиналась со всей базы."""
    project_id = active_project_id()
    if project_id is None:
        return
    wanted = set(int(value) for value in dataset_ids)
    labels = [
        dataset_label(row)
        for row in list_accessible_datasets(int(project_id))
        if int(row["id"]) in wanted
    ]
    st.session_state["statistics_scope"] = "Активный проект"
    if labels:
        st.session_state["statistics_datasets"] = labels


def render_plots_page_v0154_bridge() -> None:
    """Оставить лассо на месте и дать рядом явные пути к кластеризации и сравнению."""
    _render_base_plots()

    st.markdown("### Другие способы выделить и проверить группы")
    st.caption(
        "Лассо и рамка удобны для ручной разметки. Для независимой проверки можно открыть PCA и "
        "K-means / иерархическую / DBSCAN / HDBSCAN кластеризацию; найденные кластеры тоже сохраняются "
        "как рабочие группы и затем могут быть утверждены как Generation."
    )
    dataset_ids = _current_chemical_dataset_ids()
    c1, c2 = st.columns(2)
    if c1.button("PCA и кластеризация", width="stretch", key="v0154_plots_to_clustering"):
        _prepare_statistics_scope(dataset_ids)
        navigate("statistics")
        st.rerun()
    if c2.button("Добавить / сравнить другие данные", width="stretch", key="v0154_plots_to_compare"):
        if dataset_ids:
            st.session_state["workflow_plot_dataset_ids"] = dataset_ids
        navigate("compare")
        st.rerun()
