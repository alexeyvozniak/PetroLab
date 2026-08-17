from __future__ import annotations

from collections.abc import Mapping

import pandas as pd
import streamlit as st

from petrolab.ui.cluster_plot_handoff import CLUSTER_OVERLAY_COLUMN

from . import plots_dashboard as _plots
from . import v0160_user_ux_hotfix as _ux_chain


_PERSISTED_PLOT_CONTEXT_KEY = "_petrolab_plot_scope_context"


def _plot_context() -> dict:
    raw = st.session_state.get(_PERSISTED_PLOT_CONTEXT_KEY)
    if isinstance(raw, dict):
        return dict(raw)
    incoming = st.session_state.get("workflow_plot_context")
    return dict(incoming) if isinstance(incoming, dict) else {}


def _overlay_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    context = _plot_context()
    raw_columns = context.get("overlay_columns")
    if not isinstance(raw_columns, Mapping) or dataframe.empty or "_analysis_id" not in dataframe.columns:
        return dataframe
    out = dataframe.copy()
    ids = out["_analysis_id"].astype(str)
    for column, raw_mapping in raw_columns.items():
        if not isinstance(raw_mapping, Mapping):
            continue
        mapping = {str(key): value for key, value in raw_mapping.items()}
        out[str(column)] = ids.map(mapping)
    return out


def render_plots_page() -> None:
    """Add transient analysis-id keyed statistical overlays to the normal XY workbench."""
    original_load = _plots.load_unified_with_derived
    original_clear = _plots._clear_quick_state_for_new_scope
    original_groups = _plots._CURATED_GROUPS

    def load_with_overlay(project_id, dataset_ids):
        return _overlay_dataframe(original_load(project_id, dataset_ids))

    def clear_with_preferred_group():
        original_clear()
        preferred = str(_plot_context().get("preferred_group") or "")
        if preferred:
            st.session_state["_quick_resume_group_pending"] = preferred

    _plots.load_unified_with_derived = load_with_overlay
    _plots._clear_quick_state_for_new_scope = clear_with_preferred_group
    if CLUSTER_OVERLAY_COLUMN not in _plots._CURATED_GROUPS:
        _plots._CURATED_GROUPS = (CLUSTER_OVERLAY_COLUMN, *_plots._CURATED_GROUPS)
    try:
        _ux_chain.render_plots_page()
    finally:
        _plots.load_unified_with_derived = original_load
        _plots._clear_quick_state_for_new_scope = original_clear
        _plots._CURATED_GROUPS = original_groups
