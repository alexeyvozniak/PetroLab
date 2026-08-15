"""v0.15.1 entry-point wrappers: universal drop-zone and post-import photo handoff."""
from __future__ import annotations

import streamlit as st

from petrolab.db import list_accessible_datasets
from petrolab.ui import universal_intake as _universal
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project
from petrolab.ui.universal_intake_extensions import (
    render_image_wizard_multi_dataset,
    render_table_import_with_provenance,
)

from . import add_data as _add_data
from . import quick_import as _quick_import


def _render_table_with_locked_provenance(original_table, project_id: int, name: str, data: bytes, token: str):
    """Do not let an already-linked external provenance silently change in the same intake session."""
    source_widget_key = f"universal_source_kind_{token}"
    study_key = f"universal_study_id_{token}"
    lock_key = f"universal_locked_source_kind_{token}"
    locked_kind = st.session_state.get(lock_key)
    if locked_kind:
        st.session_state[source_widget_key] = str(locked_kind)

    result = render_table_import_with_provenance(
        original_table, project_id, name, data, token
    )

    if st.session_state.get(study_key) is not None:
        current_kind = str(st.session_state.get(source_widget_key) or "")
        if current_kind:
            st.session_state[lock_key] = current_kind
            st.caption(
                "Provenance внешнего источника уже записан и зафиксирован для этой импортированной пачки. "
                "Если источник указан неверно, исправьте его явно в «Источники и литература», а не переключателем импорта."
            )
    return result


def render_add_data_page() -> None:
    _add_data.render_add_data_page()
    project = active_project()
    if project is None:
        return

    original_table = _universal._render_table_import
    original_images = _universal._render_image_wizard

    def table_with_source(project_id: int, name: str, data: bytes, token: str):
        return _render_table_with_locked_provenance(
            original_table, project_id, name, data, token
        )

    _universal._render_table_import = table_with_source
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
        "Если фотографии относятся к нескольким автоматически разобранным фазовым наборам, откройте «Добавить данные → Универсальный +»: там dataset выбирается отдельно для каждого изображения."
    )
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
