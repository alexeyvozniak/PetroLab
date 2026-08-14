from __future__ import annotations

import streamlit as st

from petrolab.db import list_projects


ACTIVE_PROJECT_KEY = "active_project_id"
SIDEBAR_PROJECT_KEY = "sidebar_project"


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
    """Update the global context without rewriting an already-instantiated sidebar widget."""
    project_id = int(project_id)
    st.session_state[ACTIVE_PROJECT_KEY] = project_id
    if st.session_state.get(SIDEBAR_PROJECT_KEY) != project_id:
        st.session_state[SIDEBAR_PROJECT_KEY] = project_id
