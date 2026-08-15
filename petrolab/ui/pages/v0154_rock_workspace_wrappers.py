from __future__ import annotations

import streamlit as st

from petrolab.repositories.rock_repository import list_rocks
from petrolab.ui.project_context import active_project_id

from . import rocks as _rocks


def render_rocks_page() -> None:
    """Keep the proven editor, but open the rock selected in the modern workspace."""
    pending = st.session_state.pop("rock_workspace_edit_id", None)
    project_id = active_project_id()
    if pending is not None and project_id is not None:
        try:
            target_id = int(pending)
        except (TypeError, ValueError):
            target_id = -1
        for rock in list_rocks(int(project_id)):
            if int(rock["id"]) == target_id:
                st.session_state["rock_select"] = _rocks._rock_label(rock)
                break
    _rocks.render_rocks_page()
