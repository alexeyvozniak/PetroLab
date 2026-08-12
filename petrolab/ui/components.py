from __future__ import annotations

import streamlit as st

from petrolab.db import list_projects


def render_project_selector(key: str = "project_select") -> dict | None:
    """Render the shared current-project selector and return the selected project."""
    projects = list_projects()
    if not projects:
        st.info("Создайте первый проект.")
        return None
    mapping = {project["name"]: project for project in projects}
    selected_name = st.selectbox("Текущий проект", list(mapping), key=key)
    return mapping[selected_name]
