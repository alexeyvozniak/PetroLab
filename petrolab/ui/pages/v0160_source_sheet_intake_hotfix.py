from __future__ import annotations

import streamlit as st

from petrolab.ui import source_sheet_image_wizard as _sheet_wizard
from petrolab.ui import universal_intake_extensions
from petrolab.ui.layout import render_page_header
from petrolab.ui.project_context import active_project_id
from petrolab.ui.simple_image_intake import render_simple_image_intake
from petrolab.ui.source_sheet_image_wizard import render_source_sheet_image_wizard

from . import add_data as _add_data
from . import v0160_user_ux_hotfix as _ux_chain


def _source_sheet_image_gate(original):
    """Keep the explicit Next step after table import, but never before images-only intake."""
    normal_gate = _ux_chain._image_wizard_gate(original)

    def wrapped(project_id: int, image_files: list[tuple[str, bytes]], preferred_dataset_ids: list[int]) -> None:
        if str(st.session_state.get("intake_entry_mode") or "") == "Изображения":
            original(int(project_id), image_files, preferred_dataset_ids)
            return
        normal_gate(int(project_id), image_files, preferred_dataset_ids)

    return wrapped


def _compact_source_sheet_wizard(
    project_id: int,
    image_files: list[tuple[str, bytes]],
    preferred_dataset_ids: list[int],
) -> None:
    """On the dedicated image page the page title already provides the wizard heading."""
    original_header = _sheet_wizard.render_section_header
    _sheet_wizard.render_section_header = lambda *_args, **_kwargs: None
    try:
        _sheet_wizard.render_source_sheet_image_wizard(
            int(project_id), image_files, preferred_dataset_ids
        )
    finally:
        _sheet_wizard.render_section_header = original_header


def _render_images_only_page() -> None:
    project_id = active_project_id()
    render_page_header(
        "Добавить изображения",
        "Фотография → исходный лист аналитической сессии → точки → следующая фотография.",
        eyebrow="Данные",
    )
    if project_id is None:
        st.info("Сначала создайте или выберите проект.")
        return

    c1, c2 = st.columns([1, 3])
    if c1.button("← Анализы / Excel", width="stretch", key="image_intake_back_to_tables"):
        st.session_state["intake_entry_mode"] = "Анализы"
        st.rerun()
    c2.caption("Фазовые наборы выбирать не нужно: PetroLab показывает полный исходный лист.")

    original_wizard = universal_intake_extensions.render_image_wizard_multi_dataset
    universal_intake_extensions.render_image_wizard_multi_dataset = _compact_source_sheet_wizard
    try:
        render_simple_image_intake(int(project_id))
    finally:
        universal_intake_extensions.render_image_wizard_multi_dataset = original_wizard


def render_add_data_page() -> None:
    """Use a dedicated compact page for images; keep canonical table intake otherwise."""
    if str(st.session_state.get("intake_entry_mode") or "") == "Изображения":
        _render_images_only_page()
        return

    original_wizard = universal_intake_extensions.render_image_wizard_multi_dataset
    universal_intake_extensions.render_image_wizard_multi_dataset = _source_sheet_image_gate(
        render_source_sheet_image_wizard
    )
    try:
        _add_data.render_add_data_page()
    finally:
        universal_intake_extensions.render_image_wizard_multi_dataset = original_wizard
