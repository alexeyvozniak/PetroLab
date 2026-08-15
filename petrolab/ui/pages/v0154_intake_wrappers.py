"""v0.15.4 intake wrapper: complex-table staging for minerals and literature compilations."""
from __future__ import annotations

import streamlit as st

from petrolab.db import list_accessible_datasets
from petrolab.ui import universal_intake as _universal
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project
from petrolab.ui.staged_intake import render_table_import_v0154
from petrolab.ui.universal_intake_extensions import render_image_wizard_multi_dataset

from . import add_data as _add_data
from . import quick_import as _quick_import


def render_add_data_page() -> None:
    _add_data.render_add_data_page()
    project = active_project()
    if project is None:
        return

    original_table = _universal._render_table_import
    original_images = _universal._render_image_wizard

    def table_with_staging(project_id: int, name: str, data: bytes, token: str):
        return render_table_import_v0154(original_table, project_id, name, data, token)

    _universal._render_table_import = table_with_staging
    _universal._render_image_wizard = render_image_wizard_multi_dataset
    try:
        _universal.render_universal_intake(int(project["id"]))
    finally:
        _universal._render_table_import = original_table
        _universal._render_image_wizard = original_images


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
    st.caption(
        "Если к этим анализам есть BSE, EDS-карты или фотографии, их можно привязать сейчас. "
        "Для сложных литературных таблиц и блоковых заголовков используйте «Добавить данные → Универсальный +»."
    )
    dataset_id = st.selectbox(
        "К какому рабочему набору относятся фотографии",
        choices,
        format_func=lambda value: str(accessible[int(value)]["name"]),
        key="v0154_post_import_image_dataset",
    )
    if st.button("Добавить фотографии к этим анализам", type="primary", width="stretch", key="v0154_post_import_images"):
        st.session_state["workflow_image_dataset_id"] = int(dataset_id)
        navigate("images")
        st.rerun()
