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
        if name == "rock_links":
            st.session_state.pop("_pending_removed_rock_links_count", None)
        st.rerun()


def render_plot_confirmations() -> None:
    """Render pending confirmations for explicit XY destructive actions."""
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


def install() -> None:
    """Install the remaining two-click guards for rock actions only."""
    from petrolab.ui.pages import rocks

    if getattr(rocks, "_petrolab_destructive_policy_installed", False):
        return

    original_delete_rock_image = rocks.delete_rock_image
    original_set_mineral_links = rocks.set_mineral_links
    original_links_render = rocks._render_links_and_images

    def delete_rock_image(image_id: int) -> None:
        _arm_or_execute(
            "rock_image",
            int(image_id),
            lambda: original_delete_rock_image(int(image_id)),
        )

    def set_mineral_links(rock_id: int, dataset_ids) -> None:
        new_ids = tuple(sorted({int(value) for value in dataset_ids}))
        current_ids = set(int(value) for value in rocks.list_mineral_links(int(rock_id)))
        removed = current_ids - set(new_ids)
        if not removed:
            original_set_mineral_links(int(rock_id), new_ids)
            return

        target = (int(rock_id), *new_ids)
        st.session_state["_pending_removed_rock_links_count"] = len(removed)

        def action() -> None:
            original_set_mineral_links(int(rock_id), new_ids)
            st.session_state.pop("_pending_removed_rock_links_count", None)

        _arm_or_execute("rock_links", target, action)

    def render_links_and_images(rock: dict) -> None:
        pending_links = st.session_state.get(_pending_key("rock_links"))
        if pending_links is not None:
            count = int(st.session_state.get("_pending_removed_rock_links_count", 0))
            _render_pending(
                "rock_links",
                f"Будет удалено связей минерал–порода: {count}. Нажмите «Сохранить связи минерал–порода» ещё раз или отмените действие.",
            )
        _render_pending(
            "rock_image",
            "Фотография породы будет удалена с диска и из базы. Нажмите «Удалить» ещё раз или отмените действие.",
        )
        original_links_render(rock)

    rocks.delete_rock_image = delete_rock_image
    rocks.set_mineral_links = set_mineral_links
    rocks._render_links_and_images = render_links_and_images
    rocks._petrolab_destructive_policy_installed = True
