from __future__ import annotations

import streamlit as st

from petrolab.analysis_groups import clear_work_group as _clear_work_group
from petrolab.db import (
    delete_plot_recipe as _delete_plot_recipe,
    delete_style_profile as _delete_style_profile,
)


def _pending_key(name: str) -> str:
    return f"_pending_destructive_{name}"


def _confirm_then(name: str, target, action) -> bool:
    """Require the same destructive action twice, with a rerun between clicks."""
    key = _pending_key(name)
    target_value = tuple(target) if isinstance(target, (list, tuple, set)) else target
    if st.session_state.get(key) != target_value:
        st.session_state[key] = target_value
        st.rerun()
        return False
    st.session_state.pop(key, None)
    action()
    return True


def delete_plot_recipe(recipe_id: int) -> None:
    recipe_id = int(recipe_id)

    def action() -> None:
        _delete_plot_recipe(recipe_id)
        st.session_state.loaded_recipe = None
        st.session_state.plot_interactive_excluded_ids = []
        st.session_state.pop("recipe_select", None)

    _confirm_then("plot_recipe", recipe_id, action)


def delete_style_profile(profile_id: int) -> None:
    profile_id = int(profile_id)

    def action() -> None:
        _delete_style_profile(profile_id)
        st.session_state.pop("style_profile_select", None)
        for key in list(st.session_state):
            if str(key).startswith("style_editor_"):
                st.session_state.pop(key, None)

    _confirm_then("style_profile", profile_id, action)


def clear_work_group(analysis_ids) -> int:
    ids = tuple(sorted(str(value) for value in analysis_ids))
    result = {"value": 0}

    def action() -> None:
        result["value"] = int(_clear_work_group(ids))

    confirmed = _confirm_then("work_group", ids, action)
    return result["value"] if confirmed else 0
