"""v0.15.1 entry-point wrappers: universal drop-zone and post-import photo handoff."""
from __future__ import annotations

import streamlit as st

from petrolab.db import list_accessible_datasets
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project
from petrolab.ui.universal_intake import render_universal_intake

from . import add_data as _add_data
from . import quick_import as _quick_import


def render_add_data_page() -> None:
    _add_data.render_add_data_page()
    project = active_project()
    if project is not None:
        render_universal_intake(int(project["id"]))


def render_quick_import_page() -> None:
    _quick_import.render_quick_import_page()
    completed = [int(value) for value in st.session_state.get("quick_import_done_ids", [])]
    project = active_project()
    if not completed or project is None:
        return
    project_id = int(project["id"])
    accessible = {int(item["id"]): item for item in list_accessible_datasets(project_id)}
    choices = [value for value in completed if value in accessible]
    if not choices:
        return
    st.divider()
    st.markdown("### Следующий естественный шаг")
    st.caption("Если к этим анализам есть BSE, EDS-карты или фотографии, их можно привязать сейчас — по одной фотографии к одной или нескольким точкам.")
    dataset_id = st.selectbox(
        "К какому рабочему набору относятся фотографии",
        choices,
        format_func=lambda value: str(accessible[int(value)]["name"]),
        key="v0151_post_import_image_dataset",
    )
    if st.button("Добавить фотографии к этим анализам", type="primary", width="stretch", key="v0151_post_import_images"):
        st.session_state["workflow_image_dataset_id"] = int(dataset_id)
        navigate("images")
        st.rerun()
