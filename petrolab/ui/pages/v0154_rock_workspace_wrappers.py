from __future__ import annotations

import streamlit as st

from petrolab.repositories.rock_repository import list_rocks
from petrolab.ui.project_context import active_project_id

from . import rocks as _rocks


def render_rocks_page() -> None:
    """Open the technical editor on the exact rock selected in the workspace."""
    pending = st.session_state.pop("rock_workspace_edit_id", None)
    project_id = active_project_id()
    if pending is not None and project_id is not None:
        try:
            pending_id = int(pending)
        except (TypeError, ValueError):
            pending_id = None
        if pending_id is not None:
            valid_ids = {int(rock["id"]) for rock in list_rocks(int(project_id))}
            if pending_id in valid_ids:
                st.session_state["rock_selected_id"] = pending_id
    _rocks.render_rocks_page()
