from __future__ import annotations

from collections.abc import MutableMapping

import streamlit as st

from petrolab.db import list_projects


ACTIVE_PROJECT_KEY = "active_project_id"
SIDEBAR_PROJECT_KEY = "sidebar_project"

_PROJECT_TRANSIENT_EXACT = {
    "workflow_recent_import_target",
    "workflow_image_dataset_id",
    "whole_rock_workspace_context",
    "whole_rock_workspace_rock_ids",
    "rock_workspace_edit_id",
    "rock_workspace_open_id",
}
_PROJECT_TRANSIENT_PREFIXES = (
    "workflow_plot_",
    "workflow_table_",
    "workflow_edit_",
    "grain_profile_",
    "quick_import_",
    "universal_",
    "univimg_",
    "v0151_post_import_",
)


def _clear_transient_project_state(state: MutableMapping) -> list[str]:
    """Remove only identity-bearing workflow state when the active project changes."""
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
