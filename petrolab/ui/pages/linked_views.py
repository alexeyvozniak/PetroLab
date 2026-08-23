from __future__ import annotations

"""A shared research canvas for mineral and whole-rock analytical points."""

import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from petrolab.extended_plotting import (
    NORMALIZATION_REFERENCES,
    REE_ORDER,
    SPIDER_ORDER,
    build_pattern_figure,
    prepare_pattern,
)
from petrolab.interactive_plotting import PLOTLY_SYMBOLS, selected_analysis_ids
from petrolab.io_utils import numeric_candidates
from petrolab.ternary_data import prepare_ternary
from petrolab.ternary_plotting import build_interactive_ternary
from petrolab.ui.data_scope import render_analysis_scope
from petrolab.ui.layout import render_hint, render_page_header, render_section_header, render_work_context
from petrolab.ui.selection_components import (
    render_selection_mode,
    selection_action_description,
    selection_action_label,
)
from petrolab.ui.selection_context import clear_selection, read_selection, set_selection
from petrolab.ui.selection_controls import render_save_selection


_COLORS = ("#2962ff", "#e85d04", "#2a9d8f", "#9b5de5", "#d62828", "#6c757d", "#bc6c25", "#0077b6")
_SYMBOLS = ("circle", "square", "triangle-up", "diamond", "cross", "hexagon", "star", "triangle-down")


def _point_label(row: pd.Series) -> str:
    text = " · ".join(str(row.get(key) or "").strip() for key in ("Sample", "Grain", "Point") if str(row.get(key) or "").strip())
    return text or str(row.get("_analysis_id") or "")[:8]


def _categorical_columns(dataframe: pd.DataFrame) -> list[str]:
    preferred = ["Generation", "Method", "Минерал", "Rock", "Lithology", "Massif", "Источник", "Набор"]
    return [column for column in preferred if column in dataframe.columns and 1 < dataframe[column].nunique(dropna=True) <= 40]


def _mark_active(figure: go.Figure, active_ids: set[str]) -> None:
    """Use selectedpoints rather than filtering so context remains visible everywhere."""
    if not active_ids:
        return
    for trace in figure.data:
        custom = getattr(trace, "customdata", None)
        if custom is None:
            continue
        selected = [index for index, item in enumerate(custom) if str(item[0] if isinstance(item, (list, tuple)) else item) in active_ids]
        if selected:
            trace.selectedpoints = selected
            trace.selected = {"marker": {"size": 13, "opacity": 1.0, "line": {"color": "#101820", "width": 2}}}
            trace.unselected = {"marker": {"opacity": 0.18}}


def _linked_scatter(
    dataframe: pd.DataFrame, x: str, y: str, *, color_by: str | None, symbol_by: str | None, title: str,
    active_ids: set[str],
) -> go.Figure:
    work = dataframe.copy()
    work[x] = pd.to_numeric(work[x], errors="coerce")
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna(subset=[x, y])
    figure = go.Figure()
    color_values = work[color_by].fillna("Без значения").astype(str) if color_by else pd.Series("Все", index=work.index)
    symbol_values = work[symbol_by].fillna("Без значения").astype(str) if symbol_by else pd.Series("Все", index=work.index)
    color_map = {value: _COLORS[index % len(_COLORS)] for index, value in enumerate(color_values.drop_duplicates())}
    symbol_map = {value: _SYMBOLS[index % len(_SYMBOLS)] for index, value in enumerate(symbol_values.drop_duplicates())}
    for color_value in color_values.drop_duplicates():
        for symbol_value in symbol_values.drop_duplicates():
            subset = work[(color_values == color_value) & (symbol_values == symbol_value)]
            if subset.empty:
                continue
            custom = [[str(row["_analysis_id"]), _point_label(row)] for _, row in subset.iterrows()]
            name = str(color_value) if not symbol_by else f"{color_value} · {symbol_value}"
            figure.add_trace(go.Scattergl(
                x=subset[x], y=subset[y], mode="markers", name=name, customdata=custom,
                marker={"color": color_map[str(color_value)], "symbol": symbol_map[str(symbol_value)], "size": 8, "opacity": 0.86,
                        "line": {"width": 0.7, "color": "#17202a"}},
                hovertemplate=f"<b>{x}</b>: %{{x:.5g}}<br><b>{y}</b>: %{{y:.5g}}<br>%{{customdata[1]}}<extra></extra>",
            ))
    _mark_active(figure, active_ids)
    figure.update_layout(
        title=f"{title} · {len(work)} из {len(dataframe)}", height=390, margin={"l": 42, "r": 12, "t": 42, "b": 42},
        xaxis_title=x, yaxis_title=y, dragmode="lasso", clickmode="event+select",
        showlegend=False,
    )
    return figure


def _render_xy_panel(
    dataframe: pd.DataFrame, *, prefix: str, title: str, color_by: str | None, symbol_by: str | None,
    active_ids: set[str],
) -> set[str]:
    numeric = numeric_candidates(dataframe)
    if len(numeric) < 2:
        st.info("Нужны две числовые колонки.")
        return set()
    x = st.selectbox("X", numeric, key=f"{prefix}_x")
    y_options = [column for column in numeric if column != x]
    y = st.selectbox("Y", y_options, key=f"{prefix}_y")
    event = st.plotly_chart(
        _linked_scatter(dataframe, x, y, color_by=color_by, symbol_by=symbol_by, title=title, active_ids=active_ids),
        width="stretch", key=f"{prefix}_plot", on_select="rerun", selection_mode=("points", "box", "lasso"),
        config={"displaylogo": False, "scrollZoom": True},
    )
    return set(selected_analysis_ids(event))


def _render_ternary_panel(dataframe: pd.DataFrame, *, active_ids: set[str]) -> set[str]:
    numeric = numeric_candidates(dataframe)
    if len(numeric) < 3:
        st.info("Нужны три числовые колонки.")
        return set()
    a = st.selectbox("A", numeric, key="linked_ternary_a")
    b = st.selectbox("B", [item for item in numeric if item != a], key="linked_ternary_b")
    c = st.selectbox("C", [item for item in numeric if item not in {a, b}], key="linked_ternary_c")
    prepared = prepare_ternary(dataframe, a, b, c)
    if prepared.valid.empty:
        st.warning("Нет строк с тремя валидными компонентами.")
        return set()
    figure = build_interactive_ternary(
        prepared.valid, a_label=a, b_label=b, c_label=c,
        title=f"Ternary · {len(prepared.valid)} из {len(dataframe)}",
    )
    _mark_active(figure, active_ids)
    event = st.plotly_chart(
        figure, width="stretch", key="linked_ternary_plot", on_select="rerun", selection_mode=("points",),
        config={"displaylogo": False},
    )
    return set(selected_analysis_ids(event))


def _render_spider_panel(dataframe: pd.DataFrame, *, elements: tuple[str, ...], title: str, active_ids: set[str]) -> set[str]:
    reference = NORMALIZATION_REFERENCES["CI-хондрит · McDonough & Sun (1995)"]
    pattern = prepare_pattern(dataframe, elements, reference)
    if pattern.data.empty:
        st.info("Нет совместимых trace-элементов для этой панели.")
        return set()
    figure = build_pattern_figure(
        pattern, title=f"{title} · {len(pattern.data)} из {len(dataframe)}",
        ylabel="Sample / CI chondrite", log_y=True, show_legend=False, alpha=0.7,
    )
    ids = dataframe.loc[pattern.data.index, "_analysis_id"].astype(str).tolist()
    if figure.axes:
        for line, analysis_id in zip(figure.axes[0].lines, ids):
            if active_ids and analysis_id not in active_ids:
                line.set_alpha(0.14)
            elif analysis_id in active_ids:
                line.set_alpha(1.0)
                line.set_linewidth(2.2)
                line.set_zorder(10)
    st.pyplot(figure, width="stretch")
    plt.close(figure)
    labels = {_id: _point_label(dataframe.loc[index]) for index, _id in zip(pattern.data.index, ids)}
    return set(st.multiselect(
        "Кривые для отбора", ids, default=[value for value in ids if value in active_ids],
        format_func=lambda value: labels.get(value, value[:8]), key=f"linked_{title}_curves",
    ))


def _render_encoding_legend(dataframe: pd.DataFrame, *, color_by: str | None, symbol_by: str | None) -> None:
    """One compact legend, rather than six copies beneath linked panels."""
    if color_by is None and symbol_by is None:
        st.caption("Все точки отображаются одинаково. Настройте цвет или форму, если нужно сравнить группы.")
        return
    rows: list[dict[str, str]] = []
    if color_by:
        for index, value in enumerate(dataframe[color_by].fillna("Без значения").astype(str).drop_duplicates().head(16)):
            rows.append({"Кодировка": "Цвет", "Поле": color_by, "Значение": value, "Обозначение": f"вариант {index + 1}"})
    if symbol_by:
        for index, value in enumerate(dataframe[symbol_by].fillna("Без значения").astype(str).drop_duplicates().head(16)):
            rows.append({"Кодировка": "Форма", "Поле": symbol_by, "Значение": value, "Обозначение": _SYMBOLS[index % len(_SYMBOLS)]})
    if rows:
        with st.expander("Кодировка точек", expanded=False):
            st.caption("Одна общая легенда для всех панелей. В каждой панели видны только строки с совместимыми числовыми значениями.")
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=min(310, 50 + 35 * len(rows)))


def render_linked_views_page() -> None:
    render_page_header(
        "Связанные представления",
        "Один отбор переносится между бинарными, треугольными и spider-диаграммами для минералов и пород.",
        eyebrow="Исследование",
    )
    scope = render_analysis_scope("linked_views", allow_all_projects=True)
    if scope is None:
        return
    frame = scope.dataframe
    if "_analysis_id" not in frame.columns:
        st.error("В выбранных данных нет устойчивых ID анализов.")
        return

    context = read_selection()
    stored = set(context.analysis_ids) or {str(value) for value in st.session_state.get("active_selection_analysis_ids", [])}
    available = set(frame["_analysis_id"].astype(str))
    active = stored & available
    categories = _categorical_columns(frame)
    controls = st.columns([1, 1, 1, 1])
    with controls[0]:
        mode = render_selection_mode(key_prefix="linked_views", default="replace")
    color_by = controls[1].selectbox("Цвет", ["Без группировки", *categories], key="linked_color")
    symbol_by = controls[2].selectbox("Форма", ["Без группировки", *categories], key="linked_symbol")
    controls[3].metric("В рабочей выборке", len(active))
    color_by = None if color_by == "Без группировки" else color_by
    symbol_by = None if symbol_by == "Без группировки" else symbol_by
    render_work_context(
        area="выбранные наборы для связанных графиков",
        visible_count=len(frame),
        selection_count=len(stored),
        selection_visible_count=len(active),
        note="Выборка общая для таблиц, XY, ternary и spider",
    )
    render_hint("Выделите точки на XY или ternary либо выберите кривые на spider. Затем примените действие ниже. Исходные анализы, QC и фильтры не меняются.")
    _render_encoding_legend(frame, color_by=color_by, symbol_by=symbol_by)

    pending: set[str] = set()
    top = st.columns(3)
    with top[0]:
        pending |= _render_xy_panel(frame, prefix="linked_xy_a", title="XY · A", color_by=color_by, symbol_by=symbol_by, active_ids=active)
    with top[1]:
        pending |= _render_xy_panel(frame, prefix="linked_xy_b", title="XY · B", color_by=color_by, symbol_by=symbol_by, active_ids=active)
    with top[2]:
        pending |= _render_xy_panel(frame, prefix="linked_xy_c", title="XY · C", color_by=color_by, symbol_by=symbol_by, active_ids=active)
    bottom = st.columns(3)
    with bottom[0]:
        pending |= _render_ternary_panel(frame, active_ids=active)
    with bottom[1]:
        pending |= _render_spider_panel(frame, elements=REE_ORDER, title="REE spider", active_ids=active)
    with bottom[2]:
        pending |= _render_spider_panel(frame, elements=SPIDER_ORDER, title="Multi-element spider", active_ids=active)

    render_section_header("Применить выделение", "Выделенные на любой панели точки пока только подготовлены. Вы сами выбираете, что сделать с ними.")
    st.caption(f"Сейчас выделено на графиках: {len(pending)} точек. {selection_action_description(mode)}")
    left, middle, right = st.columns([1.2, 1.2, 1])
    if left.button(selection_action_label(mode), type="primary", disabled=not pending, key="linked_apply"):
        # Keep the old handoff keys for existing pages, but make SelectionContext
        # the authoritative shared object for every new interaction.
        if tuple(sorted(active)) != context.analysis_ids:
            set_selection(sorted(active), origin="Связанные представления", mode="replace")
        updated = set_selection(sorted(pending), origin="Связанные представления", mode=mode)
        st.session_state["active_selection_analysis_ids"] = list(updated.analysis_ids)
        st.session_state["selection_analysis_ids"] = list(updated.analysis_ids)
        st.success(f"Рабочая выборка: {updated.count} точек.")
        st.rerun()
    if middle.button("Очистить рабочую выборку", disabled=not stored, key="linked_clear"):
        clear_selection()
        st.session_state["active_selection_analysis_ids"] = []
        st.session_state["selection_analysis_ids"] = []
        st.rerun()
    render_save_selection(scope.project_id, sorted(active), key_prefix="linked_views", context={"chart_type": "linked_views", "dataset_ids": list(scope.dataset_ids)})
