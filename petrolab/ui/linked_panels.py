"""Связанные бинарные, треугольные и spider-панели по analysis_id."""
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


def _plotly_axis_range(limits: tuple[float, float] | list[float] | None, *, log: bool) -> list[float] | None:
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



def _panel_kind(panel: Mapping[str, object]) -> str:
    kind = str(panel.get("kind") or panel.get("type") or "xy").strip().casefold()
    return {"binary": "xy", "scatter": "xy", "triangle": "ternary", "triangular": "ternary", "ree": "spider"}.get(kind, kind)


def _panel_components(panel: Mapping[str, object], key: str) -> list[str]:
    raw = panel.get(key) or panel.get("elements" if key == "variables" else key)
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return [str(value) for value in raw if str(value).strip()]
    return []


def _is_valid_panel(dataframe: pd.DataFrame, panel: Mapping[str, object]) -> bool:
    kind = _panel_kind(panel)
    if kind == "xy":
        return panel.get("x") in dataframe.columns and panel.get("y") in dataframe.columns
    if kind == "ternary":
        values = [str(panel.get(key) or "") for key in ("a", "b", "c")]
        values = values if all(values) else _panel_components(panel, "components")
        return len(values) == 3 and all(value in dataframe.columns for value in values)
    if kind == "spider":
        values = _panel_components(panel, "variables")
        return len(values) >= 2 and all(value in dataframe.columns for value in values)
    return False


def _panel_title(panel: Mapping[str, object]) -> str:
    if str(panel.get("title") or "").strip():
        return str(panel["title"])
    kind = _panel_kind(panel)
    if kind == "ternary":
        values = [str(panel.get(key) or "") for key in ("a", "b", "c")]
        return " · ".join(values if all(values) else _panel_components(panel, "components"))
    if kind == "spider":
        return str(panel.get("y_label") or "Spider")
    return f"{panel['y']} vs {panel['x']}"


def _subplot_type(panel: Mapping[str, object]) -> str:
    return "ternary" if _panel_kind(panel) == "ternary" else "xy"


def _visual_encoding(frame: pd.DataFrame, *, color_column: str | None, marker_column: str | None, group_column: str | None):
    color_field = color_column if color_column and color_column in frame.columns else (
        group_column if group_column and group_column in frame.columns else None
    )
    if color_field:
        colors = frame[color_field].astype("string").fillna("Без группы").replace("", "Без группы")
        color_names = [str(value) for value in colors.unique().tolist()]
    else:
        colors, color_names = pd.Series(["Данные"] * len(frame), index=frame.index, dtype="string"), ["Данные"]
    color_map = {name: qualitative.Plotly[index % len(qualitative.Plotly)] for index, name in enumerate(color_names)}
    marker_field = marker_column if marker_column and marker_column in frame.columns else None
    if marker_field:
        markers = frame[marker_field].astype("string").fillna("Без значения").replace("", "Без значения")
        marker_names = [str(value) for value in markers.unique().tolist()]
    else:
        markers, marker_names = pd.Series(["Данные"] * len(frame), index=frame.index, dtype="string"), ["Данные"]
    symbols = ("circle", "square", "triangle-up", "diamond", "cross", "x", "pentagon", "star")
    marker_map = {name: symbols[index % len(symbols)] for index, name in enumerate(marker_names)}
    return colors, color_names, color_map, markers, marker_names, marker_map


def _material_scope_label(dataframe: pd.DataFrame) -> str:
    def populated(columns: tuple[str, ...]) -> bool:
        return any(column in dataframe.columns and dataframe[column].notna().any() for column in columns)
    mineral = populated(("Минерал", "Mineral", "Mineral phase", "Фаза"))
    rock = populated(("Rock", "Порода", "Lithology", "Литология", "Massif", "Массив", "Массив/комплекс", "Рабочий класс породы"))
    for column in ("Материал", "Material", "Тип материала", "Material type"):
        if column not in dataframe.columns:
            continue
        values = [str(value).casefold() for value in dataframe[column].dropna().unique().tolist()]
        mineral = mineral or any("минерал" in value or "mineral" in value for value in values)
        rock = rock or any("пород" in value or "rock" in value or "литолог" in value or "litholog" in value for value in values)
    if mineral and rock:
        return "минералы и породы"
    if rock:
        return "породы"
    if mineral:
        return "минералы"
    return "анализы"


def _ternary_components(panel: Mapping[str, object]) -> tuple[str, str, str]:
    values = [str(panel.get(key) or "") for key in ("a", "b", "c")]
    values = values if all(values) else _panel_components(panel, "components")
    return values[0], values[1], values[2]


def build_linked_panel_figure(
    dataframe: pd.DataFrame,
    panels: list[dict],
    *,
    id_column: str,
    selected_ids: Iterable[str] = (),
    group_column: str | None = None,
    color_column: str | None = None,
    marker_column: str | None = None,
    columns: int = 2,
    height_per_row: int = 330,
    dragmode: str | bool = "lasso",
    axis_limits: list[dict[str, tuple[float, float] | None]] | None = None,
    labelled_ids: Iterable[str] = (),
    excluded_ids: Iterable[str] = (),
    display_color: Mapping[str, str] | None = None,
    display_marker: Mapping[str, str] | None = None,
) -> go.Figure:
    """Build binary, ternary and spider panels over one immutable analysis ID space."""
    if id_column not in dataframe.columns:
        raise ValueError(f"Нет устойчивого идентификатора {id_column}")
    valid = [dict(panel) for panel in panels if _is_valid_panel(dataframe, panel)][:10]
    if not valid:
        raise ValueError("Нет валидных панелей")
    limits = axis_limits or [{"x": None, "y": None} for _ in valid]
    ncols = max(1, min(int(columns), 4, len(valid)))
    nrows = int(math.ceil(len(valid) / ncols))
    specs = [
        [{"type": _subplot_type(valid[index])} if index < len(valid) else {"type": "xy"} for index in range(row * ncols, (row + 1) * ncols)]
        for row in range(nrows)
    ]
    figure = make_subplots(rows=nrows, cols=ncols, subplot_titles=[_panel_title(panel) for panel in valid], specs=specs)
    selected = {_clean_id(value) for value in selected_ids if _clean_id(value)} & _available_ids(dataframe, id_column)
    legend_seen: set[str] = set()

    for panel_index, panel in enumerate(valid):
        row, col = panel_index // ncols + 1, panel_index % ncols + 1
        kind = _panel_kind(panel)
        panel_limits = limits[panel_index] if panel_index < len(limits) and isinstance(limits[panel_index], dict) else {}

        if kind == "xy":
            x, y = str(panel["x"]), str(panel["y"])
            log_x, log_y = bool(panel.get("log_x", False)), bool(panel.get("log_y", False))
            work = _panel_frame(dataframe, x, y, log_x, log_y)
            if work.empty:
                continue
            color_labels, color_names, color_map, marker_labels, marker_names, marker_map = _visual_encoding(work, color_column=color_column, marker_column=marker_column, group_column=group_column)
            for color_name in color_names:
                for marker_name in marker_names:
                    part = work.loc[(color_labels == color_name) & (marker_labels == marker_name)]
                    if part.empty:
                        continue
                    ids = [_clean_id(value) for value in part[id_column].tolist()]
                    showlegend = color_name not in legend_seen
                    figure.add_trace(go.Scattergl(
                        x=part[x], y=part[y], mode="markers", name=color_name, legendgroup=color_name, showlegend=showlegend,
                        customdata=[[value] for value in ids], text=_hover_text(part),
                        hovertemplate="%{text}<br>X: %{x}<br>Y: %{y}<extra></extra>",
                        selectedpoints=[i for i, value in enumerate(ids) if value in selected] if selected else None,
                        marker={"size": 8, "opacity": 0.88, "color": color_map[color_name], "symbol": marker_map[marker_name]},
                        selected={"marker": {"size": 13, "opacity": 1.0, "color": color_map[color_name]}},
                        unselected={"marker": {"opacity": 0.18}} if selected else None,
                        meta={"panel_kind": "xy"},
                    ), row=row, col=col)
                    if showlegend:
                        legend_seen.add(color_name)
            add_row_display_overlay(figure, work, x, y, labelled_ids=labelled_ids, excluded_ids=excluded_ids, display_color=display_color, display_marker=display_marker, row=row, col=col)
            figure.update_xaxes(title_text=str(panel.get("x_label") or x), type="log" if log_x else "linear", range=_plotly_axis_range(panel_limits.get("x"), log=log_x), row=row, col=col)
            figure.update_yaxes(title_text=str(panel.get("y_label") or y), type="log" if log_y else "linear", range=_plotly_axis_range(panel_limits.get("y"), log=log_y), row=row, col=col)
            continue

        if kind == "ternary":
            a, b, c = _ternary_components(panel)
            work = dataframe.copy()
            for component in (a, b, c):
                work[component] = pd.to_numeric(work[component], errors="coerce")
            work = work.dropna(subset=[a, b, c])
            if work.empty:
                continue
            color_labels, color_names, color_map, marker_labels, marker_names, marker_map = _visual_encoding(work, color_column=color_column, marker_column=marker_column, group_column=group_column)
            for color_name in color_names:
                for marker_name in marker_names:
                    part = work.loc[(color_labels == color_name) & (marker_labels == marker_name)]
                    if part.empty:
                        continue
                    ids = [_clean_id(value) for value in part[id_column].tolist()]
                    showlegend = color_name not in legend_seen
                    figure.add_trace(go.Scatterternary(
                        a=part[a], b=part[b], c=part[c], mode="markers", name=color_name, legendgroup=color_name, showlegend=showlegend,
                        customdata=[[value] for value in ids], text=_hover_text(part),
                        hovertemplate="%{text}<br>a: %{a}<br>b: %{b}<br>c: %{c}<extra></extra>",
                        selectedpoints=[i for i, value in enumerate(ids) if value in selected] if selected else None,
                        marker={"size": 8, "opacity": 0.88, "color": color_map[color_name], "symbol": marker_map[marker_name]},
                        selected={"marker": {"size": 13, "opacity": 1.0, "color": color_map[color_name]}},
                        unselected={"marker": {"opacity": 0.18}} if selected else None,
                        meta={"panel_kind": "ternary", "components": [a, b, c]},
                    ), row=row, col=col)
                    if showlegend:
                        legend_seen.add(color_name)
            continue

        variables = _panel_components(panel, "variables")
        log_y = bool(panel.get("log_y", True))
        work = dataframe.copy()
        for variable in variables:
            work[variable] = pd.to_numeric(work[variable], errors="coerce")
        work = work.dropna(subset=variables, how="all")
        if log_y:
            work = work.loc[(work[variables] > 0).any(axis=1)]
        if work.empty:
            continue
        color_labels, _, color_map, marker_labels, _, marker_map = _visual_encoding(work, color_column=color_column, marker_column=marker_column, group_column=group_column)
        for _, record in work.iterrows():
            analysis_id = _clean_id(record.get(id_column))
            pairs = [(variable, float(record[variable])) for variable in variables if pd.notna(record[variable]) and (not log_y or float(record[variable]) > 0)]
            if not analysis_id or len(pairs) < 2:
                continue
            xs, ys = zip(*pairs)
            color_name, marker_name = str(color_labels.loc[record.name]), str(marker_labels.loc[record.name])
            is_selected, showlegend = analysis_id in selected, color_name not in legend_seen
            figure.add_trace(go.Scatter(
                x=list(xs), y=list(ys), mode="lines+markers", name=color_name, legendgroup=color_name, showlegend=showlegend,
                customdata=[[analysis_id] for _ in xs], text=[_hover_text(work.loc[[record.name]])[0] for _ in xs],
                hovertemplate="%{text}<br>%{x}: %{y}<extra></extra>",
                line={"color": color_map[color_name], "width": 3.2 if is_selected else 1.25},
                marker={"size": 7 if is_selected else 5, "color": color_map[color_name], "symbol": marker_map[marker_name]},
                opacity=1.0 if not selected or is_selected else 0.13,
                meta={"panel_kind": "spider", "analysis_id": analysis_id},
            ), row=row, col=col)
            if showlegend:
                legend_seen.add(color_name)
        figure.update_xaxes(title_text=str(panel.get("x_label") or "Элементы"), type="category", row=row, col=col)
        figure.update_yaxes(title_text=str(panel.get("y_label") or "Нормированное содержание"), type="log" if log_y else "linear", range=_plotly_axis_range(panel_limits.get("y"), log=log_y), row=row, col=col)

    figure.update_layout(
        height=max(360, int(height_per_row) * nrows), dragmode=dragmode, clickmode="event+select",
        selectdirection="any", uirevision="petrolab-linked-panels", margin={"l": 30, "r": 20, "t": 70, "b": 35},
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

    categorical = [
        str(column) for column in dataframe.columns
        if not str(column).startswith("_") and dataframe[column].nunique(dropna=True) <= 30
        and not pd.api.types.is_numeric_dtype(dataframe[column])
    ]
    preferred = [value for value in ("PetroLab Generation", "Generation", "Рабочая группа", "Источник", "Минерал", "Mineral", "Rock", "Порода", "Lithology", "Литология", "Massif", "Массив", "Массив/комплекс", "Sample", "Grain", "Point", "Method", "Метод") if value in categorical]
    categorical = list(dict.fromkeys([*preferred, *categorical]))

    st.caption(f"Материал в текущем наборе: {_material_scope_label(visible)}. Связь панелей идёт по analysis_id, а не по типу материала.")

    c1, c2, c3 = st.columns([1.15, 1, 1])
    with c1:
        tool = st.segmented_control(
            "Инструмент", ["Точка", "Прямоугольник", "Лассо", "Панорама"],
            default="Лассо", key=f"{key}_tool",
        ) or "Лассо"
    with c2:
        color_choice = st.selectbox(
            "Цвет точек",
            ["Как в общей группировке", *categorical],
            index=0,
            key=f"{key}_color_column",
            help="Цвет и значок настраиваются независимо. Цвет задаётся значением одного поля.",
        )
    with c3:
        marker_choice = st.selectbox(
            "Значок точек",
            ["Одинаковый маркер", *categorical],
            index=0,
            key=f"{key}_marker_column",
            help="Форма значка задаётся независимо от цвета.",
        )
    mode = render_selection_mode(key_prefix=f"{key}_linked")
    color_column = group_column if color_choice == "Как в общей группировке" else str(color_choice)
    marker_column = None if marker_choice == "Одинаковый маркер" else str(marker_choice)
    dragmode: str | bool = {
        "Точка": False, "Прямоугольник": "select", "Лассо": "lasso", "Панорама": "pan",
    }.get(str(tool), "lasso")

    figure = build_linked_panel_figure(
        visible, panels, id_column=id_column, selected_ids=context.analysis_ids,
        group_column=group_column, color_column=color_column, marker_column=marker_column,
        columns=columns, dragmode=dragmode,
        axis_limits=axis_limits, labelled_ids=row_states.labelled, excluded_ids=row_states.excluded,
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
        message = f"Общий отбор: {len(visible_selected)} видимых точек; те же analysis_id подсвечиваются в бинарных, треугольных и spider-панелях."
        if hidden_count:
            message += f" Ещё {hidden_count} сейчас не видны из-за фильтра/Hide."
        c1.info(message)
        if c2.button("Очистить", key=f"{key}_clear", width="stretch"):
            clear_selection()
            st.rerun()
    else:
        st.caption("Выберите точки на любой панели — тот же Selection появится в бинарных, треугольных и spider-графиках, таблице, XY и статистике.")
    return visible_selected