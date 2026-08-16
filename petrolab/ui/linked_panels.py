"""Связанные интерактивные XY-панели с единым отбором по analysis_id."""
from __future__ import annotations

import math
from collections.abc import Iterable, Mapping

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.colors import qualitative
from plotly.subplots import make_subplots

from petrolab.interactive_plotting import add_row_display_overlay
from petrolab.ui.selection_components import render_selection_mode
from petrolab.ui.selection_context import clear_selection, read_row_states, read_selection, set_selection


def _clean_id(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _event_points(event) -> list[object] | None:
    if event is None:
        return None
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    if selection is None:
        return None
    points = getattr(selection, "points", None)
    if points is None and isinstance(selection, dict):
        points = selection.get("points")
    return list(points or [])


def selection_ids_from_event(event) -> list[str] | None:
    points = _event_points(event)
    if points is None:
        return None
    result: list[str] = []
    for point in points:
        custom = getattr(point, "customdata", None)
        if custom is None and isinstance(point, dict):
            custom = point.get("customdata")
        if isinstance(custom, (list, tuple)):
            custom = custom[0] if custom else ""
        value = _clean_id(custom)
        if value and value not in result:
            result.append(value)
    return result


def _panel_frame(dataframe: pd.DataFrame, x: str, y: str, log_x: bool, log_y: bool) -> pd.DataFrame:
    work = dataframe.copy()
    work[x] = pd.to_numeric(work[x], errors="coerce")
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna(subset=[x, y])
    if log_x:
        work = work[work[x] > 0]
    if log_y:
        work = work[work[y] > 0]
    return work


def _hover_text(frame: pd.DataFrame) -> list[str]:
    fields = [
        column for column in (
            "Sample", "Grain", "Point", "Rock", "Минерал", "Textural zone", "PetroLab Generation",
            "Generation", "Рабочая группа", "Рабочий класс породы", "Источник", "Источник / статья",
            "Источник данных", "Lithology", "Massif",
        )
        if column in frame.columns
    ]
    result: list[str] = []
    for _, row in frame.iterrows():
        parts: list[str] = []
        for field in fields:
            value = _clean_id(row.get(field))
            if value:
                parts.append(f"{field}: {value}")
        result.append("<br>".join(parts) or "Анализ")
    return result


def _group_colors(dataframe: pd.DataFrame, group_column: str | None) -> dict[str, str]:
    if not group_column or group_column not in dataframe.columns:
        return {"Данные": qualitative.Plotly[0]}
    labels = dataframe[group_column].astype("string").fillna("Без группы").replace("", "Без группы")
    names = [str(value) for value in labels.unique().tolist()]
    return {name: qualitative.Plotly[index % len(qualitative.Plotly)] for index, name in enumerate(names)}


def _available_ids(dataframe: pd.DataFrame, id_column: str) -> set[str]:
    if id_column not in dataframe.columns:
        return set()
    return {_clean_id(value) for value in dataframe[id_column].tolist() if _clean_id(value)}


def _plotly_axis_range(
    limits: tuple[float, float] | list[float] | None,
    *,
    log: bool,
) -> list[float] | None:
    if limits is None or len(limits) != 2:
        return None
    lower, upper = float(limits[0]), float(limits[1])
    if not (math.isfinite(lower) and math.isfinite(upper) and lower < upper):
        return None
    if log:
        if lower <= 0 or upper <= 0:
            return None
        return [math.log10(lower), math.log10(upper)]
    return [lower, upper]


def build_linked_panel_figure(
    dataframe: pd.DataFrame,
    panels: list[dict],
    *,
    id_column: str,
    selected_ids: Iterable[str] = (),
    group_column: str | None = None,
    columns: int = 2,
    height_per_row: int = 330,
    dragmode: str | bool = "lasso",
    axis_limits: list[dict[str, tuple[float, float] | None]] | None = None,
    labelled_ids: Iterable[str] = (),
    display_color: Mapping[str, str] | None = None,
    display_marker: Mapping[str, str] | None = None,
) -> go.Figure:
    if id_column not in dataframe.columns:
        raise ValueError(f"Нет устойчивого идентификатора {id_column}")
    valid = [dict(panel) for panel in panels if panel.get("x") in dataframe.columns and panel.get("y") in dataframe.columns]
    if not valid:
        raise ValueError("Нет валидных панелей")
    valid = valid[:10]
    limits = axis_limits or [{"x": None, "y": None} for _ in valid]
    ncols = max(1, min(int(columns), 4, len(valid)))
    nrows = int(math.ceil(len(valid) / ncols))
    titles = [str(panel.get("title") or f"{panel['y']} vs {panel['x']}") for panel in valid]
    figure = make_subplots(rows=nrows, cols=ncols, subplot_titles=titles)

    selected = {_clean_id(value) for value in selected_ids if _clean_id(value)} & _available_ids(dataframe, id_column)
    colors = _group_colors(dataframe, group_column)
    legend_seen: set[str] = set()

    for panel_index, panel in enumerate(valid):
        row = panel_index // ncols + 1
        col = panel_index % ncols + 1
        x = str(panel["x"])
        y = str(panel["y"])
        log_x = bool(panel.get("log_x", False))
        log_y = bool(panel.get("log_y", False))
        work = _panel_frame(dataframe, x, y, log_x, log_y)
        if work.empty:
            continue

        if group_column and group_column in work.columns:
            labels = work[group_column].astype("string").fillna("Без группы").replace("", "Без группы")
            groups = [(str(name), work.loc[labels == name]) for name in labels.unique().tolist()]
        else:
            groups = [("Данные", work)]

        for group_name, part in groups:
            ids = [_clean_id(value) for value in part[id_column].tolist()]
            selectedpoints = [index for index, value in enumerate(ids) if value in selected] if selected else None
            trace = go.Scattergl(
                x=part[x], y=part[y], mode="markers", name=group_name,
                legendgroup=group_name, showlegend=group_name not in legend_seen,
                customdata=[[value] for value in ids], text=_hover_text(part),
                hovertemplate="%{text}<br>X: %{x}<br>Y: %{y}<extra></extra>",
                selectedpoints=selectedpoints,
                marker={"size": 8, "opacity": 0.88, "color": colors.get(group_name)},
                selected={"marker": {"size": 13, "opacity": 1.0, "color": colors.get(group_name)}},
                unselected={"marker": {"opacity": 0.18}} if selected else None,
            )
            figure.add_trace(trace, row=row, col=col)
            legend_seen.add(group_name)

        add_row_display_overlay(
            figure, work, x, y,
            labelled_ids=labelled_ids,
            display_color=display_color,
            display_marker=display_marker,
            row=row,
            col=col,
        )

        panel_limits = limits[panel_index] if panel_index < len(limits) and isinstance(limits[panel_index], dict) else {}
        x_range = _plotly_axis_range(panel_limits.get("x"), log=log_x)
        y_range = _plotly_axis_range(panel_limits.get("y"), log=log_y)
        figure.update_xaxes(title_text=str(panel.get("x_label") or x), type="log" if log_x else "linear", range=x_range, row=row, col=col)
        figure.update_yaxes(title_text=str(panel.get("y_label") or y), type="log" if log_y else "linear", range=y_range, row=row, col=col)

    figure.update_layout(
        height=max(360, int(height_per_row) * nrows), dragmode=dragmode,
        clickmode="event+select", selectdirection="any", uirevision="petrolab-linked-panels",
        margin={"l": 30, "r": 20, "t": 70, "b": 35},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
    )
    return figure


def render_linked_panel_selection(
    dataframe: pd.DataFrame,
    panels: list[dict],
    *,
    id_column: str,
    key: str,
    group_column: str | None = None,
    columns: int = 2,
    axis_limits: list[dict[str, tuple[float, float] | None]] | None = None,
) -> list[str]:
    """Render panels backed by the global SelectionContext, never a page-local selection."""
    visible = dataframe
    row_states = read_row_states()
    if row_states.hidden and id_column in visible.columns:
        visible = visible[~visible[id_column].astype(str).isin(set(row_states.hidden))].copy()
    available = _available_ids(visible, id_column)
    context = read_selection()
    visible_selected = [value for value in context.analysis_ids if value in available]

    c1, c2 = st.columns([1.3, 1])
    with c1:
        tool = st.segmented_control(
            "Инструмент", ["Точка", "Прямоугольник", "Лассо", "Панорама"],
            default="Лассо", key=f"{key}_tool",
        ) or "Лассо"
    with c2:
        mode = render_selection_mode(key_prefix=f"{key}_linked")
    dragmode: str | bool = {
        "Точка": False, "Прямоугольник": "select", "Лассо": "lasso", "Панорама": "pan",
    }.get(str(tool), "lasso")

    figure = build_linked_panel_figure(
        visible, panels, id_column=id_column, selected_ids=context.analysis_ids,
        group_column=group_column, columns=columns, dragmode=dragmode,
        axis_limits=axis_limits, labelled_ids=row_states.labelled,
        display_color=row_states.display_color, display_marker=row_states.display_marker,
    )
    event = st.plotly_chart(
        figure, width="stretch", key=f"{key}_plotly", on_select="rerun",
        selection_mode=("points", "box", "lasso"), config={"scrollZoom": True, "displaylogo": False},
    )
    incoming = selection_ids_from_event(event)
    if incoming is not None:
        before = tuple(context.analysis_ids)
        updated = set_selection(incoming, origin="Multi-panel", mode=mode)
        if tuple(updated.analysis_ids) != before:
            st.rerun()

    context = read_selection()
    visible_selected = [value for value in context.analysis_ids if value in available]
    hidden_count = len(context.analysis_ids) - len(visible_selected)
    if context.analysis_ids:
        c1, c2 = st.columns([4, 1])
        message = f"Общий отбор: {len(visible_selected)} видимых точек; те же analysis_id подсвечиваются в других представлениях."
        if hidden_count:
            message += f" Ещё {hidden_count} сейчас не видны из-за фильтра/Hide."
        c1.info(message)
        if c2.button("Очистить", key=f"{key}_clear", width="stretch"):
            clear_selection()
            st.rerun()
    else:
        st.caption("Выберите точки на любой панели — этот же Selection появится в таблице, XY и статистике.")
    return visible_selected