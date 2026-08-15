"""Small v0.15.1 UI wrappers for exact selections and explicit point identity."""
from __future__ import annotations

import shlex

import pandas as pd
import streamlit as st

from petrolab.measurement_registry import create_entity
from petrolab.physical_point_safety import (
    _unique_marker_entity_name,
    ambiguous_marker_entity_ids,
    set_slide_marker_entity,
)
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project

from . import composite_points as _composite
from . import global_search as _search
from . import multi_panel as _multi
from . import plots_dashboard as _plots
from . import thin_section_workspace as _thin


_PLOT_EXACT_KEY = "_v0151_plot_exact_analysis_ids"
_MULTI_EXACT_KEY = "_v0151_multi_exact_analysis_ids"


def _query_tokens(query: str) -> list[str]:
    text = str(query or "").strip()
    if not text:
        return []
    try:
        values = shlex.split(text)
    except ValueError:
        values = text.split()
    return [str(value).casefold() for value in values if str(value).strip()]


def _tokenized_literal_search(dataframe: pd.DataFrame, query: str) -> pd.DataFrame:
    """AND across query tokens, OR across searchable columns for each token."""
    tokens = _query_tokens(query)
    if not tokens or dataframe.empty:
        return dataframe.iloc[0:0].copy()
    columns = _search._searchable_columns(dataframe)
    if not columns:
        return dataframe.iloc[0:0].copy()
    result_mask = pd.Series(True, index=dataframe.index, dtype=bool)
    for token in tokens:
        token_mask = pd.Series(False, index=dataframe.index, dtype=bool)
        for column in columns:
            token_mask |= dataframe[column].astype(str).str.casefold().str.contains(
                token, na=False, regex=False
            )
        result_mask &= token_mask
    return dataframe.loc[result_mask].copy()


def _tokenized_dict_matches(item: dict, query: str, keys: tuple[str, ...] | None = None) -> bool:
    tokens = _query_tokens(query)
    if not tokens:
        return False
    values = [item.get(key) for key in keys] if keys else [
        value for key, value in item.items() if not str(key).startswith("_")
    ]
    haystack = " ".join(str(value or "") for value in values).casefold()
    return all(token in haystack for token in tokens)


def _update_exact_selection_state(state, persistent_key: str) -> list[str]:
    """Persist a routed exact selection across Streamlit reruns until explicitly reset."""
    has_analysis_route = "workflow_plot_analysis_ids" in state
    has_dataset_route = "workflow_plot_dataset_ids" in state
    if has_dataset_route and not has_analysis_route:
        state.pop(persistent_key, None)
    if has_analysis_route:
        incoming = [str(value) for value in state.get("workflow_plot_analysis_ids", []) if str(value)]
        if incoming:
            state[persistent_key] = list(dict.fromkeys(incoming))
        else:
            state.pop(persistent_key, None)
    persisted = [str(value) for value in state.get(persistent_key, []) if str(value)]
    if persisted:
        # Legacy pages consume this key with pop(); restore it on every rerun.
        state["workflow_plot_analysis_ids"] = persisted
    return persisted


def _search_context_actions(result: pd.DataFrame, scope_label: str) -> None:
    if result.empty or "_analysis_id" not in result.columns:
        return
    analysis_ids = result["_analysis_id"].astype(str).drop_duplicates().tolist()
    dataset_ids = sorted({
        int(value) for value in result.get("_dataset_id", pd.Series(dtype=int)).dropna().tolist()
    })
    context = {
        "scope": scope_label,
        "query": str(st.session_state.get("global_search_query") or ""),
        "analysis_ids": analysis_ids,
        "dataset_ids": dataset_ids,
    }
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("Один XY", type="primary", width="stretch", key="global_search_plot"):
        st.session_state["workflow_plot_dataset_ids"] = dataset_ids
        st.session_state["workflow_plot_analysis_ids"] = analysis_ids
        st.session_state["workflow_plot_context"] = context
        st.session_state["workflow_plot_notice"] = "В график передан точный результат поиска."
        navigate("plots")
        st.rerun()
    if c2.button("2–6 графиков", width="stretch", key="global_search_multi"):
        st.session_state["workflow_plot_dataset_ids"] = dataset_ids
        st.session_state["workflow_plot_analysis_ids"] = analysis_ids
        st.session_state["workflow_plot_context"] = context
        st.session_state["multi_panel_data_mode"] = "Обычные анализы"
        navigate("multi_panel")
        st.rerun()
    if c3.button("Таблица статьи", width="stretch", key="global_search_table"):
        st.session_state["workflow_table_dataset_ids"] = dataset_ids
        st.session_state["workflow_table_analysis_ids"] = analysis_ids
        st.session_state["workflow_table_context"] = context
        navigate("article_tables")
        st.rerun()
    if c4.button("Редактировать", width="stretch", key="global_search_edit"):
        st.session_state["workflow_edit_dataset_ids"] = dataset_ids
        st.session_state["workflow_edit_analysis_ids"] = analysis_ids
        st.session_state["workflow_edit_context"] = context
        navigate("analyses")
        st.rerun()


def render_global_search_page() -> None:
    original_literal = _search._literal_search
    original_dict = _search._dict_matches
    original_actions = _search._context_actions
    _search._literal_search = _tokenized_literal_search
    _search._dict_matches = _tokenized_dict_matches
    _search._context_actions = _search_context_actions
    try:
        _search.render_global_search_page()
    finally:
        _search._literal_search = original_literal
        _search._dict_matches = original_dict
        _search._context_actions = original_actions


def _render_exact_selection_notice(persistent_key: str, exact: list[str], reset_key: str) -> None:
    if not exact:
        return
    st.info(
        f"Активен точный отбор: {len(exact)} analysis_id. Он сохраняется при изменении осей и стилей и не расширяется обратно до всего dataset."
    )
    if st.button("Сбросить точный отбор", key=reset_key, width="stretch"):
        st.session_state.pop(persistent_key, None)
        st.session_state.pop("workflow_plot_analysis_ids", None)
        st.rerun()


def render_plots_page() -> None:
    exact = _update_exact_selection_state(st.session_state, _PLOT_EXACT_KEY)
    original_quick = _plots._quick_workspace

    def quick_with_exact(project_id: int) -> None:
        _render_exact_selection_notice(_PLOT_EXACT_KEY, exact, "v0151_reset_xy_exact")
        original_quick(project_id)

    _plots._quick_workspace = quick_with_exact
    try:
        _plots.render_plots_dashboard_page()
    finally:
        _plots._quick_workspace = original_quick


def render_multi_panel_page() -> None:
    exact = _update_exact_selection_state(st.session_state, _MULTI_EXACT_KEY)
    original_raw = _multi._raw_dataframe

    def raw_with_exact(project_id: int):
        dataframe, selected_ids = original_raw(project_id)
        routed = {
            str(value) for value in st.session_state.pop("workflow_plot_analysis_ids", exact)
            if str(value)
        }
        if routed and not dataframe.empty and "_analysis_id" in dataframe.columns:
            dataframe = dataframe[dataframe["_analysis_id"].astype(str).isin(routed)].copy()
            st.caption(f"Точный отбор сохранён: {len(dataframe)} строк после фильтра analysis_id.")
        _render_exact_selection_notice(_MULTI_EXACT_KEY, exact, "v0151_reset_multi_exact")
        return dataframe, selected_ids

    _multi._raw_dataframe = raw_with_exact
    try:
        _multi.render_multi_panel_page()
    finally:
        _multi._raw_dataframe = original_raw


def _explicit_marker_link_panel() -> None:
    project = active_project()
    if project is None:
        return
    project_id = int(project["id"])
    section_id = st.session_state.get("thin_section_selected")
    image_id = st.session_state.get("thin_image_selected")
    if section_id is None or image_id is None:
        return

    from petrolab.composite_points import list_physical_points
    from petrolab.slides import list_slide_markers

    markers = list_slide_markers(project_id, slide_image_id=int(image_id))
    points = list_physical_points(project_id, thin_section_id=int(section_id))
    ambiguous = ambiguous_marker_entity_ids(project_id)
    ambiguous_here = [
        marker for marker in markers
        if marker.get("entity_id") is not None and int(marker["entity_id"]) in ambiguous
    ]
    if ambiguous_here:
        st.warning(
            "Найдена старая неоднозначная связь: несколько маркеров были объединены только из-за одинаковой подписи. Такие точки исключены из composite до явного решения ниже."
        )
    if not markers:
        return
    with st.expander("Физическая идентичность маркера", expanded=bool(ambiguous_here)):
        st.caption(
            "Одинаковая подпись P-1 на двух снимках сама по себе ничего не объединяет. Выберите одну существующую физическую точку только если это действительно одно и то же место."
        )
        marker_by_id = {int(item["id"]): item for item in markers}
        marker_id = st.selectbox(
            "Маркер",
            list(marker_by_id),
            format_func=lambda value: str(marker_by_id[int(value)].get("label") or f"Маркер {value}"),
            key=f"v0151_marker_identity_{image_id}",
        )
        marker = marker_by_id[int(marker_id)]
        point_by_id = {int(item["id"]): item for item in points}
        current = marker.get("entity_id")
        options = list(point_by_id)
        if options:
            default_index = options.index(int(current)) if current is not None and int(current) in point_by_id else 0
            point_id = st.selectbox(
                "Это та же физическая точка, что…",
                options,
                index=default_index,
                format_func=lambda value: str(point_by_id[int(value)]["name"]),
                key=f"v0151_marker_target_{image_id}_{marker_id}",
            )
            if st.button("Подтвердить физическую связь", type="primary", width="stretch", key=f"v0151_marker_link_{marker_id}"):
                try:
                    set_slide_marker_entity(project_id, int(marker_id), int(point_id))
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.success("Физическая связь подтверждена явно.")
                    st.rerun()

        if current is not None and int(current) in ambiguous:
            if st.button("Сделать этот маркер отдельной физической точкой", width="stretch", key=f"v0151_split_marker_{marker_id}"):
                try:
                    name = _unique_marker_entity_name(project_id, int(section_id), marker)
                    section = next(
                        (item for item in _thin.list_entities(project_id) if int(item["id"]) == int(section_id)),
                        None,
                    )
                    point_id = create_entity(
                        project_id, kind="probe_point", name=name,
                        sample_id=section.get("sample_id") if section else None,
                        parent_id=int(section_id),
                        description="Явно отделено от неоднозначной связи v0.15",
                    )
                    set_slide_marker_entity(project_id, int(marker_id), int(point_id))
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.success("Маркер теперь отдельная физическая точка.")
                    st.rerun()


def render_thin_section_workspace_page() -> None:
    _thin.render_thin_section_workspace_page()
    _explicit_marker_link_panel()


def render_composite_points_page() -> None:
    project = active_project()
    if project is not None:
        ambiguous = ambiguous_marker_entity_ids(int(project["id"]))
        if ambiguous:
            st.error(
                f"Неоднозначных старых physical point: {len(ambiguous)}. PetroLab не включает их в composite автоматически. Откройте «Работать со шлифом» и подтвердите или разделите маркеры."
            )
            if st.button("Разобрать связи в шлифе", key="v0151_composite_fix_links"):
                navigate("thin_section")
                st.rerun()
    _composite.render_composite_points_page()
