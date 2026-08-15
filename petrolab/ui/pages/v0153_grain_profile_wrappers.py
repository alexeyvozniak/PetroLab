from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project_id

from . import v0151_wrappers as _v0151


def _search_actions_with_profile(result: pd.DataFrame, scope_label: str) -> None:
    if result.empty or "_analysis_id" not in result.columns:
        return
    analysis_ids = result["_analysis_id"].astype(str).drop_duplicates().tolist()
    dataset_ids = sorted({
        int(value) for value in result.get("_dataset_id", pd.Series(dtype=int)).dropna().tolist()
    })
    context = {
        "project_id": active_project_id(),
        "scope": scope_label,
        "query": str(st.session_state.get("global_search_query") or ""),
        "analysis_ids": analysis_ids,
        "dataset_ids": dataset_ids,
    }
    c1, c2, c3, c4, c5 = st.columns(5)
    if c1.button("Один XY", type="primary", width="stretch", key="global_search_plot"):
        st.session_state["workflow_plot_dataset_ids"] = dataset_ids
        st.session_state["workflow_plot_analysis_ids"] = analysis_ids
        st.session_state["workflow_plot_context"] = context
        st.session_state["workflow_plot_notice"] = "В график передан точный результат поиска."
        navigate("plots")
        st.rerun()
    if c2.button("2–6 графиков", width="stretch", key="global_search_multi"):
        st.session_state["workflow_plot_dataset_ids"] = dataset_ids
        st.session_state["workflow_plot_analysis_ids"] = analysis_ids
        st.session_state["workflow_plot_context"] = context
        st.session_state["multi_panel_data_mode"] = "Обычные анализы"
        navigate("multi_panel")
        st.rerun()
    if c3.button("Профиль", width="stretch", key="global_search_grain_profile"):
        st.session_state["grain_profile_dataset_ids"] = dataset_ids
        st.session_state["grain_profile_analysis_ids"] = analysis_ids
        st.session_state["grain_profile_context"] = context
        navigate("grain_profile")
        st.rerun()
    if c4.button("Таблица статьи", width="stretch", key="global_search_table"):
        st.session_state["workflow_table_dataset_ids"] = dataset_ids
        st.session_state["workflow_table_analysis_ids"] = analysis_ids
        st.session_state["workflow_table_context"] = context
        navigate("article_tables")
        st.rerun()
    if c5.button("Редактировать", width="stretch", key="global_search_edit"):
        st.session_state["workflow_edit_dataset_ids"] = dataset_ids
        st.session_state["workflow_edit_analysis_ids"] = analysis_ids
        st.session_state["workflow_edit_context"] = context
        navigate("analyses")
        st.rerun()


def render_global_search_page() -> None:
    original = _v0151._search_context_actions
    _v0151._search_context_actions = _search_actions_with_profile
    try:
        _v0151.render_global_search_page()
    finally:
        _v0151._search_context_actions = original
