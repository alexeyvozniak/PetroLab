from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN
from petrolab.source_registry import (
    SOURCE_LABEL_COLUMN,
    filter_visible_sources,
    source_labels,
)


_MISSING_VALUE = "— без значения —"


@dataclass(frozen=True)
class PlotVisibilityDimension:
    key: str
    label: str
    column: str


_VISIBILITY_DIMENSIONS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("source", "Источник / статья", (SOURCE_LABEL_COLUMN,)),
    ("sample", "Sample", ("Sample", "Образец")),
    (
        "generation",
        "Generation",
        ("PetroLab Generation", "Generation", "Генерация"),
    ),
    ("mineral", "Минерал", ("Минерал",)),
    ("work_group", "Рабочая группа", (WORK_GROUP_COLUMN,)),
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


def _visibility_tokens(series: pd.Series) -> pd.Series:
    values = series.astype("string").fillna("").map(lambda value: str(value).strip())
    return values.mask(values.eq(""), _MISSING_VALUE)


def _display_visibility_value(value: str) -> str:
    return "Без значения" if str(value) == _MISSING_VALUE else str(value)


def available_visibility_dimensions(dataframe: pd.DataFrame) -> list[PlotVisibilityDimension]:
    """Return stable visibility dimensions that are actually present in the current plot data."""
    result: list[PlotVisibilityDimension] = []
    for key, label, candidates in _VISIBILITY_DIMENSIONS:
        column = next((candidate for candidate in candidates if candidate in dataframe.columns), None)
        if column is None:
            continue
        values = _visibility_tokens(dataframe[column])
        if values.empty:
            continue
        result.append(PlotVisibilityDimension(key=key, label=label, column=column))
    return result


def _visibility_options(dataframe: pd.DataFrame, dimension: PlotVisibilityDimension) -> list[str]:
    if dimension.column not in dataframe.columns:
        return []
    return sorted(_visibility_tokens(dataframe[dimension.column]).unique().tolist(), key=str.casefold)


def normalize_visibility_filters(
    dataframe: pd.DataFrame,
    filters: dict[str, list[str]] | None,
) -> dict[str, list[str]]:
    """Prune stale values without turning a changed dataset selection into an accidental blank plot."""
    raw = filters if isinstance(filters, dict) else {}
    normalized: dict[str, list[str]] = {}
    for dimension in available_visibility_dimensions(dataframe):
        if dimension.key not in raw:
            continue
        requested = raw.get(dimension.key)
        if not isinstance(requested, list):
            continue
        options = _visibility_options(dataframe, dimension)
        if not requested:
            normalized[dimension.key] = []
            continue
        valid = [str(value) for value in requested if str(value) in options]
        if not valid:
            # All saved values disappeared after the user changed datasets/search.
            # Treat that filter as stale rather than silently hiding every point.
            continue
        if set(valid) != set(options):
            normalized[dimension.key] = valid
    return normalized


def apply_plot_visibility_filters(
    dataframe: pd.DataFrame,
    filters: dict[str, list[str]] | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply reversible plot-only visibility filters without mutating analytical rows."""
    normalized = normalize_visibility_filters(dataframe, filters)
    if dataframe.empty or not normalized:
        return dataframe.copy(), dataframe.iloc[0:0].copy()

    visible_mask = pd.Series(True, index=dataframe.index, dtype=bool)
    for dimension in available_visibility_dimensions(dataframe):
        if dimension.key not in normalized:
            continue
        allowed = set(normalized[dimension.key])
        tokens = _visibility_tokens(dataframe[dimension.column])
        visible_mask &= tokens.isin(allowed)

    return dataframe.loc[visible_mask].copy(), dataframe.loc[~visible_mask].copy()


def _legacy_source_filter(
    dataframe: pd.DataFrame,
    saved_visible: list[str] | None,
) -> dict[str, list[str]]:
    if saved_visible is None or SOURCE_LABEL_COLUMN not in dataframe.columns:
        return {}
    options = source_labels(dataframe)
    valid = [value for value in saved_visible if value in options]
    if not saved_visible:
        return {"source": []}
    if valid and set(valid) != set(options):
        return {"source": valid}
    return {}


def render_source_visibility_controls(
    dataframe: pd.DataFrame,
    *,
    key: str,
    saved_visible: list[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str], list[str]]:
    """Render one reversible visibility panel shared by quick and advanced XY plots.

    The historical function name and return shape are preserved because publication manifests
    still track source visibility explicitly. The UI now also controls Sample, Generation,
    mineral and work-group visibility from the same plot-only panel.
    """
    source_options = source_labels(dataframe)
    dimensions = available_visibility_dimensions(dataframe)
    if not dimensions:
        return dataframe.copy(), dataframe.iloc[0:0].copy(), [], []

    state_key = f"{key}_visibility_filters"
    if state_key not in st.session_state:
        st.session_state[state_key] = _legacy_source_filter(dataframe, saved_visible)
    state = normalize_visibility_filters(dataframe, st.session_state.get(state_key, {}))
    st.session_state[state_key] = state

    dimension_map = {dimension.key: dimension for dimension in dimensions}
    dimension_key = f"{key}_visibility_dimension"
    dimension_keys = list(dimension_map)
    current_dimension = st.session_state.get(dimension_key)
    if current_dimension not in dimension_map:
        current_dimension = "source" if "source" in dimension_map else dimension_keys[0]
        st.session_state[dimension_key] = current_dimension

    st.markdown("#### Что показывать")
    selector_col, reset_col = st.columns([4, 1], vertical_alignment="bottom")
    with selector_col:
        current_dimension = st.selectbox(
            "Управлять видимостью по",
            dimension_keys,
            key=dimension_key,
            format_func=lambda value: dimension_map[value].label,
            help=(
                "Один блок управляет временной видимостью статей, Sample, Generation, минералов "
                "и рабочих групп. Ограничения разных категорий можно сочетать."
            ),
        )
    with reset_col:
        if st.button(
            "Включить все",
            key=f"{key}_show_all",
            disabled=not state,
            help="Сбросить все ограничения видимости и вернуть на график все доступные точки.",
            width="stretch",
        ):
            st.session_state[state_key] = {}
            for dimension in dimensions:
                widget_key = f"{key}_visibility_values_{dimension.key}"
                st.session_state[widget_key] = _visibility_options(dataframe, dimension)
            st.rerun()

    active = dimension_map[current_dimension]
    options = _visibility_options(dataframe, active)
    counts = _visibility_tokens(dataframe[active.column]).value_counts().to_dict()
    default_values = state.get(active.key, options)
    widget_key = f"{key}_visibility_values_{active.key}"
    if widget_key not in st.session_state:
        st.session_state[widget_key] = default_values
    else:
        previous = list(st.session_state[widget_key])
        valid_previous = [value for value in previous if value in options]
        if previous and not valid_previous:
            # Dataset/search context changed completely; do not keep a stale empty selector.
            valid_previous = default_values
        if valid_previous != previous:
            st.session_state[widget_key] = valid_previous

    visible_values = st.multiselect(
        "Статьи и источники на графике" if active.key == "source" else "Что оставить на графике",
        options,
        key=widget_key,
        format_func=lambda value: (
            f"{_display_visibility_value(value)} · "
            f"{_russian_count(int(counts.get(value, 0)), ('точка', 'точки', 'точек'))}"
        ),
        help=(
            "Снимите значения, чтобы временно убрать соответствующие точки только на текущий график "
            "и из его экспорта. Анализы, QC, связи и интерпретации не меняются — данные остаются в базе."
        ),
    )
    if set(visible_values) == set(options):
        state.pop(active.key, None)
    else:
        state[active.key] = list(visible_values)
    state = normalize_visibility_filters(dataframe, state)
    st.session_state[state_key] = state

    visible, _all_hidden = apply_plot_visibility_filters(dataframe, state)

    # Keep the historical source-only excluded frame so the advanced export does not falsely
    # label Sample/Generation/mineral visibility exclusions as "source disabled".
    selected_sources = state.get("source", source_options)
    selected_sources = [value for value in source_options if value in set(selected_sources)]
    source_visible_frame, source_hidden_frame = filter_visible_sources(dataframe, selected_sources)
    del source_visible_frame
    hidden_sources = [value for value in source_options if value not in set(selected_sources)]

    active_summary: list[str] = []
    for dimension in dimensions:
        if dimension.key not in state:
            continue
        total = len(_visibility_options(dataframe, dimension))
        selected = len(state[dimension.key])
        active_summary.append(f"{dimension.label}: {selected}/{total}")

    visible_count = len(visible)
    total_count = len(dataframe)
    summary = " · ".join(active_summary)
    if summary:
        st.caption(
            f"Видно {_russian_count(visible_count, ('точка', 'точки', 'точек'))} из {total_count}. "
            f"Активно: {summary}. Это влияет только на текущий график и экспорт; данные остаются в базе."
        )
    else:
        st.caption(
            f"Видно {_russian_count(visible_count, ('точка', 'точки', 'точек'))} из {total_count}. "
            "Можно переключить категорию выше и выключить источник, Sample, Generation, минерал "
            "или рабочую группу без изменения базы."
        )

    return visible, source_hidden_frame, selected_sources, hidden_sources
