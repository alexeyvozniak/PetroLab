from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.source_registry import (
    SOURCE_LABEL_COLUMN,
    filter_visible_sources,
    source_labels,
)


def render_source_visibility_controls(
    dataframe: pd.DataFrame,
    *,
    key: str,
    saved_visible: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
    """Render one reversible source selector shared by quick and advanced plots."""
    options = source_labels(dataframe)
    if not options:
        return dataframe.copy(), dataframe.iloc[0:0].copy(), [], []

    counts = dataframe[SOURCE_LABEL_COLUMN].astype(str).value_counts().to_dict()
    widget_key = f"{key}_visible_sources"
    show_all, hide_all = st.columns(2)
    if show_all.button("Показать все источники", key=f"{key}_show_all", width="stretch"):
        st.session_state[widget_key] = options
    if hide_all.button("Скрыть все источники", key=f"{key}_hide_all", width="stretch"):
        st.session_state[widget_key] = []

    if widget_key in st.session_state:
        current = [value for value in st.session_state[widget_key] if value in options]
        if current != list(st.session_state[widget_key]):
            st.session_state[widget_key] = current
    requested_defaults = options if saved_visible is None else saved_visible
    defaults = [value for value in requested_defaults if value in options]
    visible_sources = st.multiselect(
        "👁 Видимые статьи / источники",
        options,
        default=defaults,
        key=widget_key,
        format_func=lambda value: f"{value} · {int(counts.get(value, 0))} точек",
        help=(
            "Удалите источник из списка, чтобы временно убрать все его точки. "
            "Исходные анализы, QC и привязка к статье не изменятся."
        ),
    )
    visible, hidden = filter_visible_sources(dataframe, visible_sources)
    hidden_sources = [value for value in options if value not in set(visible_sources)]
    if hidden_sources:
        st.caption(
            f"В этом графике выключено источников: {len(hidden_sources)}; "
            f"скрыто точек: {len(hidden)}. Данные остаются в базе."
        )
    else:
        st.caption("Все источники включены. Нажатие на легенду меняет только экранный preview; этот список управляет также экспортом.")
    return visible, hidden, list(visible_sources), hidden_sources
