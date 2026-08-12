from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.db import create_project, list_projects


def render_projects_page() -> None:
    """Render project creation and project-list UI."""
    st.title("Проекты")

    with st.form("new_project", clear_on_submit=True):
        name = st.text_input("Название проекта")
        description = st.text_area("Краткое описание")
        if st.form_submit_button("Создать проект", type="primary"):
            try:
                create_project(name, description)
                st.success(f"Проект «{name.strip()}» создан.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    projects = list_projects()
    if not projects:
        return

    st.dataframe(
        pd.DataFrame(projects)[["name", "description", "created_at"]],
        width="stretch",
        hide_index=True,
    )
