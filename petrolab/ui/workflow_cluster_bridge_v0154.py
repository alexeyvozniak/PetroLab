"""Переходы между мультипанельным обзором, лассо, кластеризацией и Generation."""
from __future__ import annotations

import streamlit as st

from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_accessible_datasets
from petrolab.ui import universal_intake_extensions as _extensions
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project_id
from petrolab.ui import workflow_continuity_v0154 as _flow


_CHEMICAL_MARKUP_MODE = "v0154_chemical_markup_mode"


def _current_chemical_dataset_ids() -> list[int]:
    """Вернуть наборы текущей химической работы, не подмешивая чужие данные проекта."""
    recipe = st.session_state.get("loaded_recipe") or {}
    raw = recipe.get("dataset_ids") if isinstance(recipe, dict) else None
    if not raw:
        raw = st.session_state.get("workflow_plot_dataset_ids", []) or []
    result: list[int] = []
    for value in raw or []:
        try:
            dataset_id = int(value)
        except (TypeError, ValueError):
            continue
        if dataset_id not in result:
            result.append(dataset_id)
    return result


def _prepare_statistics_scope(dataset_ids: list[int]) -> None:
    """Передать в статистику ровно текущие наборы, чтобы кластеризация не начиналась со всей базы."""
    project_id = active_project_id()
    if project_id is None:
        return
    wanted = set(int(value) for value in dataset_ids)
    labels = [
        dataset_label(row)
        for row in list_accessible_datasets(int(project_id))
        if int(row["id"]) in wanted
    ]
    st.session_state["statistics_scope"] = "Активный проект"
    if labels:
        st.session_state["statistics_datasets"] = labels


def _reset_multi_panel_state() -> None:
    """Не переносить фильтры и оси старой мультипанели на только что импортированные данные."""
    for key in list(st.session_state):
        if str(key).startswith("multi_panel_"):
            st.session_state.pop(key, None)


def _chemistry_entry_route(route: str, chemical_mode: bool) -> str:
    """После импорта начинать исследование химии с мультипанельного обзора."""
    return "multi_panel" if route == "plots" and chemical_mode else route


def render_add_data_page_v0154_bridge() -> None:
    """Перенаправить кнопку «Исследовать химию» с одиночного XY сразу на мультипанель."""
    original_navigate = _flow.navigate
    original_flow_batch_token = _flow._batch_token
    project_id = active_project_id()
    original_extension_batch_token = _extensions._batch_token

    # После синхронизации с новым intake transient-ключи изображений разделены по проектам.
    # Textural zone должна вычислять тот же ключ, иначе фото и выбранные точки окажутся в разных state-ветках.
    if project_id is not None:
        def scoped_flow_batch_token(image_files: list[tuple[str, bytes]]) -> str:
            return f"p{int(project_id)}_{original_extension_batch_token(image_files)}"

        _flow._batch_token = scoped_flow_batch_token

    def navigate_from_import(route: str) -> None:
        target = _chemistry_entry_route(
            str(route),
            bool(st.session_state.get(_CHEMICAL_MARKUP_MODE, False)),
        )
        if target == "multi_panel":
            _reset_multi_panel_state()
            st.session_state["workflow_plot_notice"] = (
                "Открыты только что импортированные наборы сразу в нескольких химических проекциях. "
                "Textural zone доступна как наблюдаемая группировка; для точного ручного отбора ниже есть переход к лассо."
            )
        original_navigate(target)

    _flow.navigate = navigate_from_import
    try:
        _flow.render_add_data_page_v0154()
    finally:
        _flow.navigate = original_navigate
        _flow._batch_token = original_flow_batch_token


def _render_multi_panel_with_texture() -> None:
    """Сохранить новый Textural zone поверх актуальной публикационной мультипанели, если она уже есть."""
    from petrolab.ui.pages import multi_panel as _multi

    try:
        from petrolab.ui.pages import v0152_publication_wrappers as _publication
    except ImportError:
        _publication = None

    if _publication is None:
        _flow.render_multi_panel_page_v0154()
        return

    original_raw = _multi._raw_dataframe

    def raw_with_texture(project_id: int):
        dataframe, dataset_ids = original_raw(project_id)
        return _flow.overlay_textural_zone(dataframe), dataset_ids

    _multi._raw_dataframe = raw_with_texture
    try:
        _publication.render_multi_panel_page()
    finally:
        _multi._raw_dataframe = original_raw


def render_multi_panel_page_v0154_bridge() -> None:
    """Сделать мультипанель первым экраном химического исследования и сохранить пути к точной разметке."""
    chemical_mode = bool(st.session_state.get(_CHEMICAL_MARKUP_MODE, False))
    notice = st.session_state.pop("workflow_plot_notice", "") if chemical_mode else ""
    if notice:
        st.success(str(notice))

    _render_multi_panel_with_texture()

    if not chemical_mode:
        return

    dataset_ids = _current_chemical_dataset_ids()
    st.divider()
    st.markdown("### Продолжить разметку")
    st.caption(
        "Мультипанель нужна для одновременной проверки одной и той же выборки в нескольких проекциях. "
        "Если границу группы нужно провести вручную, откройте точную разметку лассо; для независимой проверки — PCA и кластеризацию."
    )
    c1, c2, c3 = st.columns(3)
    if c1.button("Точная разметка лассо", type="primary", width="stretch", key="v0154_multi_to_lasso"):
        if dataset_ids:
            st.session_state["workflow_plot_dataset_ids"] = dataset_ids
        navigate("plots")
        st.rerun()
    if c2.button("PCA и кластеризация", width="stretch", key="v0154_multi_to_clustering"):
        _prepare_statistics_scope(dataset_ids)
        navigate("statistics")
        st.rerun()
    if c3.button("Утвердить Generation", width="stretch", key="v0154_multi_to_generation"):
        st.session_state.pop(_CHEMICAL_MARKUP_MODE, None)
        navigate("generations")
        st.rerun()


def render_plots_page_v0154_bridge() -> None:
    """Оставить лассо на месте и дать рядом явные пути к кластеризации и сравнению."""
    _flow.render_plots_page_v0154()

    st.markdown("### Другие способы выделить и проверить группы")
    st.caption(
        "Лассо и рамка удобны для ручной разметки. Для независимой проверки можно открыть PCA и "
        "K-means / иерархическую / DBSCAN / HDBSCAN кластеризацию; найденные кластеры тоже сохраняются "
        "как рабочие группы и затем могут быть утверждены как Generation."
    )
    dataset_ids = _current_chemical_dataset_ids()
    c1, c2 = st.columns(2)
    if c1.button("PCA и кластеризация", width="stretch", key="v0154_plots_to_clustering"):
        _prepare_statistics_scope(dataset_ids)
        navigate("statistics")
        st.rerun()
    if c2.button("Добавить / сравнить другие данные", width="stretch", key="v0154_plots_to_compare"):
        if dataset_ids:
            st.session_state["workflow_plot_dataset_ids"] = dataset_ids
        navigate("compare")
        st.rerun()
