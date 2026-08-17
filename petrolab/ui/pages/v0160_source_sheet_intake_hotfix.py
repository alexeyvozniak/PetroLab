from __future__ import annotations

import streamlit as st

from petrolab.ui import universal_intake_extensions
from petrolab.ui.source_sheet_image_wizard import render_source_sheet_image_wizard

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


def render_add_data_page() -> None:
    """Use source-sheet analysis universe and a direct images-only entry."""
    original_wizard = universal_intake_extensions.render_image_wizard_multi_dataset
    original_gate = _ux_chain._image_wizard_gate
    universal_intake_extensions.render_image_wizard_multi_dataset = render_source_sheet_image_wizard
    _ux_chain._image_wizard_gate = _source_sheet_image_gate
    try:
        _ux_chain.render_add_data_page()
    finally:
        universal_intake_extensions.render_image_wizard_multi_dataset = original_wizard
        _ux_chain._image_wizard_gate = original_gate
