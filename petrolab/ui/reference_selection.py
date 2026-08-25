from __future__ import annotations

import hashlib

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import set_work_group
from petrolab.ui.navigation import navigate
from petrolab.ui.selection_context import clear_selection, read_selection, set_selection


_SELECTION_COLUMN = "Выбрать"


def _selection_token(values) -> str:
    payload = "\x1f".join(sorted(str(value) for value in values))
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]


def _sync_mirrors(analysis_ids) -> None:
    values = [str(value) for value in analysis_ids]
    st.session_state["selection_analysis_ids"] = values
    st.session_state["active_selection_analysis_ids"] = values


def render_manual_selection_table(
    dataframe: pd.DataFrame,
    *,
    key_prefix: str,
    origin: str,
    columns: list[str] | None = None,
    height: int = 420,
    max_rows: int | None = None,
) -> pd.DataFrame:
    """Render a reference-style table with an explicit checkbox selection column.

    The checkbox state is the same transient Selection used by linked plots,
    statistics and thin-section views. Rows outside the current table remain in
    Selection when the user changes visible checkboxes, so filtering never
    silently discards an off-screen scientific selection.
    """
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        st.dataframe(dataframe, width="stretch", hide_index=True, height=height)
        return dataframe.iloc[0:0].copy()

    source = dataframe.copy()
    if max_rows is not None and len(source) > int(max_rows):
        source = source.head(int(max_rows)).copy()
        st.caption(f"Показаны первые {int(max_rows):,} строк. Сузьте фильтр, чтобы выбрать остальные.".replace(",", " "))

    source["_analysis_id"] = source["_analysis_id"].astype(str)
    context = read_selection()
    selected_now = set(context.analysis_ids)
    visible_ids = source["_analysis_id"].astype(str).tolist()
    visible_set = set(visible_ids)

    view = source.copy()
    view.insert(0, _SELECTION_COLUMN, [analysis_id in selected_now for analysis_id in visible_ids])
    if columns is None:
        display_columns = [column for column in view.columns if not str(column).startswith("_")]
    else:
        display_columns = [column for column in columns if column in view.columns]
    ordered = [_SELECTION_COLUMN, "_analysis_id", *[column for column in display_columns if column not in {_SELECTION_COLUMN, "_analysis_id"}]]
    ordered = list(dict.fromkeys(column for column in ordered if column in view.columns))
    view = view[ordered]

    toolbar = st.columns([1.15, 1.15, 5.7])
    if toolbar[0].button("Выбрать все видимые", key=f"{key_prefix}_select_all", width="stretch"):
        outside = [analysis_id for analysis_id in context.analysis_ids if analysis_id not in visible_set]
        updated = set_selection([*outside, *visible_ids], origin=origin, mode="replace", label=context.label, metadata=context.metadata)
        _sync_mirrors(updated.analysis_ids)
        st.rerun()
    if toolbar[1].button("Снять видимые", key=f"{key_prefix}_clear_visible", width="stretch"):
        outside = [analysis_id for analysis_id in context.analysis_ids if analysis_id not in visible_set]
        updated = set_selection(outside, origin=origin, mode="replace", label=context.label, metadata=context.metadata)
        _sync_mirrors(updated.analysis_ids)
        st.rerun()
    toolbar[2].caption("Отмечайте строки галочками. Выбор сразу общий для таблиц, графиков, статистики и шлифов.")

    token = _selection_token(context.analysis_ids)
    edited = st.data_editor(
        view,
        width="stretch",
        hide_index=True,
        height=height,
        num_rows="fixed",
        disabled=[column for column in view.columns if column != _SELECTION_COLUMN],
        column_config={
            _SELECTION_COLUMN: st.column_config.CheckboxColumn("", help="Добавить анализ в общую рабочую выборку"),
            "_analysis_id": None,
        },
        key=f"{key_prefix}_manual_selection_{token}",
    )

    checked = [
        analysis_id
        for analysis_id, value in zip(visible_ids, edited[_SELECTION_COLUMN].fillna(False).astype(bool).tolist())
        if value
    ]
    previous_visible = [analysis_id for analysis_id in context.analysis_ids if analysis_id in visible_set]
    if set(checked) != set(previous_visible):
        outside = [analysis_id for analysis_id in context.analysis_ids if analysis_id not in visible_set]
        updated = set_selection([*outside, *checked], origin=origin, mode="replace", label=context.label, metadata=context.metadata)
        _sync_mirrors(updated.analysis_ids)
        st.rerun()

    wanted = set(read_selection().analysis_ids)
    return dataframe[dataframe["_analysis_id"].astype(str).isin(wanted)].copy()


def render_selection_action_bar(
    dataframe: pd.DataFrame,
    *,
    key_prefix: str,
    project_id: int | None = None,
    show_images: bool = True,
    show_statistics: bool = False,
) -> None:
    """Compact bottom tray matching the approved Product Design reference."""
    context = read_selection()
    if not context.analysis_ids:
        return

    selected = dataframe.iloc[0:0].copy()
    if not dataframe.empty and "_analysis_id" in dataframe.columns:
        selected = dataframe[dataframe["_analysis_id"].astype(str).isin(set(context.analysis_ids))].copy()

    with st.container(border=True):
        columns = st.columns([1.45, 1.05, 1.05 if show_images else .01, 1.05 if show_statistics else .01, 1.05, .72])
        columns[0].markdown(f"**Выбрано: {context.count} анализов**")
        columns[0].caption("Общая рабочая выборка")

        if columns[1].button("Показать на графиках", type="primary", key=f"{key_prefix}_to_linked", width="stretch"):
            _sync_mirrors(context.analysis_ids)
            if not selected.empty and "_dataset_id" in selected.columns:
                st.session_state["workflow_plot_dataset_ids"] = list(dict.fromkeys(int(value) for value in pd.to_numeric(selected["_dataset_id"], errors="coerce").dropna().tolist()))
            st.session_state["workflow_plot_analysis_ids"] = list(context.analysis_ids)
            navigate("linked_views")
            st.rerun()

        if show_images:
            if columns[2].button("Показать изображения", key=f"{key_prefix}_to_images", width="stretch"):
                _sync_mirrors(context.analysis_ids)
                navigate("slides")
                st.rerun()

        if show_statistics:
            target = columns[3]
            if target.button("Статистика", key=f"{key_prefix}_to_statistics", width="stretch"):
                if not selected.empty and "_dataset_id" in selected.columns:
                    st.session_state["statistics_dataset_ids_pending"] = list(dict.fromkeys(int(value) for value in pd.to_numeric(selected["_dataset_id"], errors="coerce").dropna().tolist()))
                navigate("statistics")
                st.rerun()

        with columns[4].popover("Сохранить группу"):
            group_name = st.text_input(
                "Название группы",
                key=f"{key_prefix}_group_name",
                placeholder="например, каймы флогопита",
            ).strip()
            st.caption("Рабочая группа не меняет Generation и исходную химию.")
            if st.button("Сохранить", type="primary", disabled=not group_name, key=f"{key_prefix}_save_group", width="stretch"):
                changed = set_work_group(context.analysis_ids, group_name)
                st.success(f"В группу «{group_name}» сохранено: {changed}.")

        if columns[5].button("Очистить", key=f"{key_prefix}_clear", width="stretch"):
            clear_selection()
            _sync_mirrors([])
            st.rerun()
