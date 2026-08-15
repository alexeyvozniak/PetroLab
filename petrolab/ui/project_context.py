from __future__ import annotations

from collections.abc import MutableMapping

import streamlit as st

from petrolab.db import list_projects


ACTIVE_PROJECT_KEY = "active_project_id"
SIDEBAR_PROJECT_KEY = "sidebar_project"

# Identity-bearing state must never survive a real project switch. Keep
# presentation preferences (colors, publication presets, generic appearance)
# out of this list, but reset scientific object/data identities and assumptions.
_PROJECT_TRANSIENT_EXACT = {
    "pending_study_id",
    "thin_section_selected",
    "thin_image_selected",
    "thin_image_focus_id_pending",
    "composite_section",
    "composite_point",
    "multi_panel_section",
    "mixed_dataset",
    "formula_dataset",
    "formula_method",
    "img_dataset",
    "workflow_dataset",
    "workspace_sample",
    "workspace_dataset",
    "db_datasets_dashboard",
    "db_search_dashboard",
    "batch_edit_datasets",
    "quick_plot_datasets",
    "multi_panel_datasets",
    "unified_editor_dashboard",
    "analysis_table_thermodynamic_point",
    "active_analytical_session",
    "analytical_session_selector",
    "loaded_ternary_recipe",
    "workflow_recent_import_target",
    "workflow_image_dataset_id",
    "whole_rock_workspace_context",
    "whole_rock_workspace_rock_ids",
    "rock_workspace_edit_id",
    "rock_workspace_open_id",
    "workspace_sample_id_pending",
    "workspace_dataset_id_pending",
    "thin_section_focus_id_pending",
    "thin_section_sample_id_pending",
    "multi_panel_thin_section_id",
    "_v0151_plot_exact_analysis_ids",
    "_v0151_multi_exact_analysis_ids",
    "_audit_edit_exact_analysis_ids",
    "_audit_edit_exact_dataset_ids",
    "_audit_edit_exact_context",
    "_audit_table_exact_analysis_ids",
    "_audit_table_exact_dataset_ids",
    "_audit_table_exact_context",
    "_audit_batch_exact_analysis_ids",
    "_audit_batch_exact_dataset_ids",
}
_PROJECT_TRANSIENT_PREFIXES = (
    # workflow_* is exclusively project-local hand-off/recent-action state.
    "workflow_",
    # Object/annotation widgets contain project-local ids or scientific choices.
    "workspace_",
    "thin_",
    "slide_",
    "composite_",
    "mixed_",
    "batch_",
    "imgwiz_",
    "session_",
    "generation_",
    "grain_profile_",
    "thermodynamics_",
    "equilibrium_",
    "ratio_",
    "ternary_",
    "exchange_",
    # Destructive confirmation must never carry into a different project.
    "_pending_destructive_",
    # Import wizards contain dataset/project identities.
    "quick_import_",
    "universal_",
    "univimg_",
    "v0151_post_import_",
    # Database-browser filters are a selection of rows in one project.
    "db_selection_",
)


def _clear_transient_project_state(state: MutableMapping) -> list[str]:
    """Remove project-bound workflow state on a real project switch.

    This is a data-integrity boundary, not cosmetic cleanup. Streamlit widget
    state can otherwise override a freshly routed id or silently keep an old
    filter/selection after the user changes projects.
    """
    removed: list[str] = []
    for key in list(state.keys()):
        text = str(key)
        if text in _PROJECT_TRANSIENT_EXACT or any(text.startswith(prefix) for prefix in _PROJECT_TRANSIENT_PREFIXES):
            state.pop(key, None)
            removed.append(text)
    return removed


def active_project() -> dict | None:
    """Return the global sidebar project without rendering a second selector."""
    projects = list_projects()
    if not projects:
        st.session_state.pop(ACTIVE_PROJECT_KEY, None)
        return None
    by_id = {int(project["id"]): project for project in projects}
    ids = list(by_id)
    try:
        project_id = int(st.session_state.get(ACTIVE_PROJECT_KEY, ids[0]))
    except (TypeError, ValueError):
        project_id = ids[0]
    if project_id not in by_id:
        project_id = ids[0]
    st.session_state[ACTIVE_PROJECT_KEY] = project_id
    if st.session_state.get(SIDEBAR_PROJECT_KEY) not in by_id:
        st.session_state[SIDEBAR_PROJECT_KEY] = project_id
    return by_id[project_id]


def active_project_id() -> int | None:
    project = active_project()
    return None if project is None else int(project["id"])


def active_project_name(fallback: str = "Проект не выбран") -> str:
    project = active_project()
    return fallback if project is None else str(project.get("name") or fallback)


def set_active_project(project_id: int) -> None:
    """Update global context and drop transient identities only on a real project switch."""
    project_id = int(project_id)
    previous = st.session_state.get(ACTIVE_PROJECT_KEY)
    try:
        previous_id = None if previous is None else int(previous)
    except (TypeError, ValueError):
        previous_id = None
    if previous_id is not None and previous_id != project_id:
        _clear_transient_project_state(st.session_state)
    st.session_state[ACTIVE_PROJECT_KEY] = project_id
    if st.session_state.get(SIDEBAR_PROJECT_KEY) != project_id:
        st.session_state[SIDEBAR_PROJECT_KEY] = project_id
