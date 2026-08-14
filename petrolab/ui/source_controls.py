from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.source_registry import (
    SOURCE_LABEL_COLUMN,
    filter_visible_sources,
    source_labels,
)


def _russian_count(value: int, forms: tuple[str, str, str]) -> str:
    """Format a compact Russian count without adding a UI dependency elsewhere."""
    number = abs(int(value))
    if number % 10 == 1 and number % 100 != 11:
        form = forms[0]
    elif number % 10 in {2, 3, 4} and number % 100 not in {12, 13, 14}:
        form = forms[1]
    else:
        form = forms[2]
    return f"{value} {form}"


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

    if widget_key in st.session_state:
        current = [value for value in st.session_state[widget_key] if value in options]
        if current != list(st.session_state[widget_key]):
            st.session_state[widget_key] = current
    requested_defaults = options if saved_visible is None else saved_visible
    defaults = [value for value in requested_defaults if value in options]
    selected_before_render = list(st.session_state.get(widget_key, defaults))
    selector, action = st.columns([4, 1], vertical_alignment="bottom")
    with action:
        if st.button(
            "Включить все",
            key=f"{key}_show_all",
            disabled=set(selected_before_render) == set(options),
            help="Вернуть на график все доступные статьи и источники.",
            width="stretch",
        ):
            st.session_state[widget_key] = options
    with selector:
        default_config = {"default": defaults} if widget_key not in st.session_state else {}
        visible_sources = st.multiselect(
            "Статьи и источники на графике",
            options,
            key=widget_key,
            format_func=lambda value: (
                f"{value} · {_russian_count(int(counts.get(value, 0)), ('точка', 'точки', 'точек'))}"
            ),
            help=(
                "Снимите публикацию, чтобы убрать её точки из графика и экспорта. "
                "Исходные анализы, QC и привязка к статье останутся в базе."
            ),
            **default_config,
        )
    visible, hidden = filter_visible_sources(dataframe, visible_sources)
    hidden_sources = [value for value in options if value not in set(visible_sources)]
    if hidden_sources:
        st.caption(
            f"На графике: {_russian_count(len(visible_sources), ('источник', 'источника', 'источников'))} "
            f"из {len(options)} · вне графика: {_russian_count(len(hidden), ('точка', 'точки', 'точек'))}. "
            "Это влияет только на текущий график и его экспорт — данные остаются в базе."
        )
    else:
        st.caption(
            f"На графике: {_russian_count(len(options), ('источник', 'источника', 'источников'))} из {len(options)}. "
            "Снимите публикацию из списка, чтобы временно убрать её из графика и экспорта."
        )
    return visible, hidden, list(visible_sources), hidden_sources
