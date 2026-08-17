from __future__ import annotations

import streamlit as st

from petrolab.ui.navigation import navigate

from . import object_workspace as _workspace
from . import v0160_user_ux_hotfix as _ux_chain


def render_object_workspace_page() -> None:
    """Expose image intake where the user is already working with analytical data."""
    original_header = _workspace.render_page_header

    def header_with_image_action(*args, **kwargs):
        original_header(*args, **kwargs)
        action, spacer = st.columns([1.15, 3])
        if action.button(
            "+ Добавить изображения",
            type="primary",
            width="stretch",
            key="workspace_add_images",
            help="Добавить PPL/XPL/BSE/карты к уже загруженным аналитическим точкам.",
        ):
            st.session_state["intake_entry_mode"] = "Изображения"
            navigate("add_data")
            st.rerun()
        spacer.empty()

    _workspace.render_page_header = header_with_image_action
    try:
        _ux_chain.render_object_workspace_page()
    finally:
        _workspace.render_page_header = original_header
