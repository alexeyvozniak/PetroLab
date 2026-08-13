from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from petrolab.analysis_groups import WORK_GROUP_COLUMN


PLOTLY_SYMBOLS = {
    "o": "circle", "s": "square", "^": "triangle-up", "D": "diamond",
    "v": "triangle-down", "P": "cross", "X": "x", "<": "triangle-left",
    ">": "triangle-right", "h": "hexagon", "*": "star", "p": "pentagon", "8": "octagon",
}
_GROUP_COLORS = (
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
)


def _text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def _marker_symbol(style: Mapping[str, Any] | None) -> str:
    return PLOTLY_SYMBOLS.get(str((style or {}).get("marker", "o")), "circle")


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
    if "_analysis_id" not in dataframe.columns:
        raise ValueError("Для интерактивного выбора требуется _analysis_id")
    if x not in dataframe.columns or y not in dataframe.columns:
        raise ValueError("Выбранные оси отсутствуют в таблице")

    work = dataframe.copy()
    work[x] = pd.to_numeric(work[x], errors="coerce").replace([np.inf, -np.inf], np.nan)
    work[y] = pd.to_numeric(work[y], errors="coerce").replace([np.inf, -np.inf], np.nan)
    work = work.dropna(subset=[x, y])
    if log_x:
        work = work[work[x] > 0]
    if log_y:
        work = work[work[y] > 0]

    hover_columns = [
        column for column in ["Sample", "Grain", "Point", "Generation", "Набор", WORK_GROUP_COLUMN]
        if column in work.columns
    ]

    if group_col and group_col in work.columns:
        labels = work[group_col].astype("string").fillna("Без группы").replace("", "Без группы")
        groups = [(name, work[labels == name]) for name in labels.unique().tolist()]
    else:
        groups = [("Все точки", work)]

    figure = go.Figure()
    for group_index, (group_name, subset) in enumerate(groups):
        if subset.empty:
            continue
        style = dict((style_map or {}).get(str(group_name), {}))
        style.setdefault("color", _GROUP_COLORS[group_index % len(_GROUP_COLORS)])
        customdata = [
            [str(row["_analysis_id"])] + [_text(row.get(column)) for column in hover_columns]
            for _, row in subset.iterrows()
        ]
        hover_lines = [f"<b>{x_label or x}</b>: %{{x}}", f"<b>{y_label or y}</b>: %{{y}}"]
        for index, column in enumerate(hover_columns, start=1):
            hover_lines.append(f"<b>{column}</b>: %{{customdata[{index}]}}")
        hover_lines.append("<extra></extra>")
        figure.add_trace(
            go.Scattergl(
                x=subset[x], y=subset[y], mode="markers", name=str(group_name),
                customdata=customdata,
                marker={
                    "size": _marker_size(style),
                    "symbol": _marker_symbol(style),
                    "opacity": float(style.get("alpha", 0.9) or 0.9),
                    "color": style["color"],
                    "line": {"width": 1},
                },
                hovertemplate="<br>".join(hover_lines),
                selected={"marker": {"opacity": 1.0, "size": _marker_size(style) + 3.0}},
                unselected={"marker": {"opacity": 0.35}},
            )
        )

    figure.update_layout(
        title=title or None, xaxis_title=x_label or x, yaxis_title=y_label or y,
        dragmode="lasso", clickmode="event+select", selectdirection="any",
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
        analysis_id = customdata[0] if isinstance(customdata, (list, tuple)) and customdata else customdata
        value = str(analysis_id).strip()
        if value and value not in selected:
            selected.append(value)
    return selected
