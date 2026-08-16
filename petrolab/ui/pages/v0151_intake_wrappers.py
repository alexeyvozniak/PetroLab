"""Compatibility entry points for the legacy quick-import route.

Canonical Add Data lives in pages/add_data.py + ui/intake_workflow.py. This
module intentionally contains no runtime module-function reassignment.
"""
from __future__ import annotations

import streamlit as st

from petrolab.db import list_accessible_datasets
from petrolab.ui.intake_workflow import render_recent_import_undo
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project

from .add_data import render_add_data_page
from . import quick_import as _quick_import


def render_quick_import_page() -> None:
    """Legacy deep-link kept for compatibility; normal users use Add Data."""
    _quick_import.render_quick_import_page()
    completed = [int(value) for value in st.session_state.get("quick_import_done_ids", [])]
    project = active_project()
    if project is None:
        return
    project_id = int(project["id"])
    render_recent_import_undo(project_id)
    if not completed:
        return

    recent_target = st.session_state.get("workflow_recent_import_target")
    if recent_target is not None:
        try:
            if int(recent_target) != project_id:
                return
        except (TypeError, ValueError):
            return

    accessible = {int(item["id"]): item for item in list_accessible_datasets(project_id)}
    choices = [value for value in completed if value in accessible]
    if not choices:
        return
    st.divider()
    st.markdown("### Следующий естественный шаг")
    st.caption(
        "Если к этим анализам есть BSE, EDS-карты или фотографии, откройте основной экран «Добавить данные»: "
        "там изображения связываются с конкретными рабочими наборами и точками."
    )
    dataset_id = st.selectbox(
        "К какому рабочему набору относятся фотографии",
        choices,
        format_func=lambda value: str(accessible[int(value)]["name"]),
        key=f"v0154_post_import_image_dataset_{project_id}",
    )
    if st.button(
        "Добавить фотографии к этим анализам",
        type="primary",
        width="stretch",
        key=f"v0154_post_import_images_{project_id}",
    ):
        st.session_state["workflow_image_dataset_id"] = int(dataset_id)
        navigate("add_data")
        st.rerun()
