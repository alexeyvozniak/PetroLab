from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd
import plotly.graph_objects as go

from petrolab.analysis_groups import WORK_GROUP_COLUMN


PLOTLY_SYMBOLS = {
    "o": "circle",
    "s": "square",
    "^": "triangle-up",
    "D": "diamond",
    "v": "triangle-down",
    "P": "cross",
    "X": "x",
    "<": "triangle-left",
    ">": "triangle-right",
    "h": "hexagon",
    "*": "star",
    "p": "pentagon",
    "8": "octagon",
}


def _text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def _marker_symbol(style: Mapping[str, Any] | None) -> str:
    marker = str((style or {}).get("marker", "o"))
    return PLOTLY_SYMBOLS.get(marker, "circle")


def _marker_size(style: Mapping[str, Any] | None, base_size: float = 9.0) -> float:
    multiplier = float((style or {}).get("size_multiplier", 1.0) or 1.0)
    return max(5.0, min(28.0, base_size * multiplier))


def build_interactive_scatter(
    dataframe: pd.DataFrame,
    x: str,
    y: str,
    group_col: str | None = None,
    *,
    x_label: str | None = None,
    y_label: str | None = None,
    title: str = "",
    log_x: bool = False,
    log_y: bool = False,
    style_map: Mapping[str, Mapping[str, Any]] | None = None,
) -> go.Figure:
    """Build a diagnostic Plotly scatter with immutable analysis IDs in customdata.

    This figure is for selection/inspection. Publication rendering remains Matplotlib-based.
    """
    if "_analysis_id" not in dataframe.columns:
        raise ValueError("Для интерактивного выбора требуется _analysis_id")
    if x not in dataframe.columns or y not in dataframe.columns:
        raise ValueError("Выбранные оси отсутствуют в таблице")

    work = dataframe.copy()
    work[x] = pd.to_numeric(work[x], errors="coerce")
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna(subset=[x, y])

    hover_columns = [
        column
        for column in [
            "Sample",
            "Grain",
            "Point",
            "Generation",
            "Набор",
            WORK_GROUP_COLUMN,
        ]
        if column in work.columns
    ]

    if group_col and group_col in work.columns:
        group_values = work[group_col].fillna("").astype(str)
        groups = [(name if name else "Без группы", work[group_values == name]) for name in group_values.unique()]
    else:
        groups = [("Все точки", work)]

    figure = go.Figure()
    for group_name, subset in groups:
        if subset.empty:
            continue
        style = (style_map or {}).get(str(group_name), {})
        customdata = []
        for _, row in subset.iterrows():
            customdata.append(
                [str(row["_analysis_id"])] + [_text(row.get(column)) for column in hover_columns]
            )

        hover_lines = [f"<b>{x_label or x}</b>: %{{x}}", f"<b>{y_label or y}</b>: %{{y}}"]
        for index, column in enumerate(hover_columns, start=1):
            hover_lines.append(f"<b>{column}</b>: %{{customdata[{index}]}}")
        hover_lines.append("<extra></extra>")

        figure.add_trace(
            go.Scattergl(
                x=subset[x],
                y=subset[y],
                mode="markers",
                name=str(group_name),
                customdata=customdata,
                marker={
                    "size": _marker_size(style),
                    "symbol": _marker_symbol(style),
                    "opacity": float(style.get("alpha", 0.9) or 0.9),
                    "line": {"width": 1},
                },
                hovertemplate="<br>".join(hover_lines),
                selected={"marker": {"opacity": 1.0, "size": _marker_size(style) + 3.0}},
                unselected={"marker": {"opacity": 0.35}},
            )
        )

    figure.update_layout(
        title=title or None,
        xaxis_title=x_label or x,
        yaxis_title=y_label or y,
        dragmode="lasso",
        clickmode="event+select",
        selectdirection="any",
        margin={"l": 55, "r": 20, "t": 50 if title else 20, "b": 55},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0},
        height=610,
    )
    if log_x:
        figure.update_xaxes(type="log")
    if log_y:
        figure.update_yaxes(type="log")
    return figure


def selected_analysis_ids(event: Any) -> list[str]:
    """Extract immutable analysis IDs from a Streamlit Plotly selection event."""
    if event is None:
        return []

    try:
        selection = event.get("selection", {})
    except AttributeError:
        selection = getattr(event, "selection", {}) or {}
    try:
        points = selection.get("points", [])
    except AttributeError:
        points = getattr(selection, "points", []) or []

    selected: list[str] = []
    for point in points or []:
        try:
            customdata = point.get("customdata")
        except AttributeError:
            customdata = getattr(point, "customdata", None)
        if customdata is None:
            continue
        if isinstance(customdata, (list, tuple)):
            if not customdata:
                continue
            analysis_id = customdata[0]
        else:
            analysis_id = customdata
        value = str(analysis_id).strip()
        if value and value not in selected:
            selected.append(value)
    return selected
