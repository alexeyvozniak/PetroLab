from __future__ import annotations

import streamlit as st

from petrolab.analysis_groups import clear_work_group as _clear_work_group
from petrolab.db import (
    delete_plot_recipe as _delete_plot_recipe,
    delete_style_profile as _delete_style_profile,
)
from petrolab.ui.destructive_actions import confirm_then, pending_key, render_pending


def render_plot_confirmations() -> None:
    render_pending(
        "plot_recipe",
        "Удаление рецепта нельзя отменить. Нажмите «Удалить рецепт» ещё раз для подтверждения или отмените действие.",
    )
    render_pending(
        "style_profile",
        "Удаление профиля стилей нельзя отменить. Нажмите «Удалить выбранный профиль» ещё раз или отмените действие.",
    )
    pending_group = st.session_state.get(pending_key("work_group"))
    if pending_group is not None:
        render_pending(
            "work_group",
            f"Рабочая группа будет снята с {len(pending_group)} точек. Нажмите кнопку очистки ещё раз или отмените действие.",
        )


def delete_plot_recipe(recipe_id: int) -> None:
    recipe_id = int(recipe_id)

    def action() -> None:
        _delete_plot_recipe(recipe_id)
        st.session_state.loaded_recipe = None
        st.session_state.plot_interactive_excluded_ids = []
        st.session_state.pop("recipe_select", None)

    confirm_then("plot_recipe", recipe_id, action)


def delete_style_profile(profile_id: int) -> None:
    profile_id = int(profile_id)

    def action() -> None:
        _delete_style_profile(profile_id)
        st.session_state.pop("style_profile_select", None)
        for key in list(st.session_state):
            if str(key).startswith("style_editor_"):
                st.session_state.pop(key, None)

    confirm_then("style_profile", profile_id, action)


def clear_work_group(analysis_ids) -> int:
    ids = tuple(sorted(str(value) for value in analysis_ids))
    result = {"value": 0}

    def action() -> None:
        result["value"] = int(_clear_work_group(ids))

    confirmed = confirm_then("work_group", ids, action)
    return result["value"] if confirmed else 0
