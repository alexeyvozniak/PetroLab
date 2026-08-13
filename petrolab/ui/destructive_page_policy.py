from __future__ import annotations

import streamlit as st


def _pending_key(name: str) -> str:
    return f"_pending_destructive_{name}"


def _arm_or_execute(name: str, target, action) -> None:
    key = _pending_key(name)
    target_value = tuple(target) if isinstance(target, (list, tuple, set)) else target
    if st.session_state.get(key) != target_value:
        st.session_state[key] = target_value
        st.rerun()
    st.session_state.pop(key, None)
    action()


def _render_pending(name: str, text: str) -> None:
    key = _pending_key(name)
    if key not in st.session_state:
        return
    st.warning(text)
    if st.button("Отмена", key=f"cancel_{name}"):
        st.session_state.pop(key, None)
        st.rerun()


def install() -> None:
    """Install two-click guards for destructive legacy actions once per process."""
    from petrolab.ui.pages import plots, rocks

    if getattr(plots, "_petrolab_destructive_policy_installed", False):
        return

    original_delete_recipe = plots.delete_plot_recipe
    original_delete_profile = plots.delete_style_profile
    original_clear_group = plots.clear_work_group
    original_plot_render = plots.render_plots_page

    def delete_recipe(recipe_id: int) -> None:
        def action() -> None:
            original_delete_recipe(int(recipe_id))
            st.session_state.loaded_recipe = None
            st.session_state.plot_interactive_excluded_ids = []
            st.session_state.pop("recipe_select", None)

        _arm_or_execute("plot_recipe", int(recipe_id), action)

    def delete_profile(profile_id: int) -> None:
        def action() -> None:
            original_delete_profile(int(profile_id))
            st.session_state.pop("style_profile_select", None)
            for key in list(st.session_state):
                if str(key).startswith("style_editor_"):
                    st.session_state.pop(key, None)

        _arm_or_execute("style_profile", int(profile_id), action)

    def clear_group(analysis_ids) -> int:
        ids = tuple(sorted(str(value) for value in analysis_ids))
        result: dict[str, int] = {"value": 0}

        def action() -> None:
            result["value"] = int(original_clear_group(ids))

        _arm_or_execute("work_group", ids, action)
        return result["value"]

    def render_plots() -> None:
        _render_pending(
            "plot_recipe",
            "Удаление рецепта нельзя отменить. Нажмите «Удалить рецепт» ещё раз для подтверждения или отмените действие.",
        )
        _render_pending(
            "style_profile",
            "Удаление профиля стилей нельзя отменить. Нажмите «Удалить выбранный профиль» ещё раз или отмените действие.",
        )
        pending_group = st.session_state.get(_pending_key("work_group"))
        if pending_group is not None:
            _render_pending(
                "work_group",
                f"Рабочая группа будет снята с {len(pending_group)} точек. Нажмите кнопку очистки ещё раз или отмените действие.",
            )
        original_plot_render()

    plots.delete_plot_recipe = delete_recipe
    plots.delete_style_profile = delete_profile
    plots.clear_work_group = clear_group
    plots.render_plots_page = render_plots

    original_delete_rock_image = rocks.delete_rock_image
    original_links_render = rocks._render_links_and_images

    def delete_rock_image(image_id: int) -> None:
        _arm_or_execute(
            "rock_image",
            int(image_id),
            lambda: original_delete_rock_image(int(image_id)),
        )

    def render_links_and_images(rock: dict) -> None:
        _render_pending(
            "rock_image",
            "Фотография породы будет удалена с диска и из базы. Нажмите «Удалить» ещё раз или отмените действие.",
        )
        original_links_render(rock)

    rocks.delete_rock_image = delete_rock_image
    rocks._render_links_and_images = render_links_and_images
    plots._petrolab_destructive_policy_installed = True
