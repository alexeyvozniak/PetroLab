from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from petrolab.analysis_groups import WORK_GROUP_COLUMN
from petrolab.group_envelopes import compute_group_envelope
from petrolab.group_styles import default_group_color, display_group_series
from petrolab.source_registry import SOURCE_LABEL_COLUMN


PLOTLY_SYMBOLS = {
    "o": "circle", "s": "square", "^": "triangle-up", "D": "diamond",
    "v": "triangle-down", "P": "cross", "X": "x", "<": "triangle-left",
    ">": "triangle-right", "h": "hexagon", "*": "star", "p": "pentagon", "8": "octagon",
}


def _text(value: Any) -> str:
    if pd.isna(value):
        return ""
    return str(value)


def _marker_symbol(style: Mapping[str, Any] | None) -> str:
    return PLOTLY_SYMBOLS.get(str((style or {}).get("marker", "o")), "circle")


def _marker_size(style: Mapping[str, Any] | None, base_size: float = 9.0) -> float:
    multiplier = float((style or {}).get("size_multiplier", 1.0) or 1.0)
    return max(5.0, min(28.0, base_size * multiplier))


def _outline_color(style: Mapping[str, Any] | None) -> str:
    value = str((style or {}).get("outline_color", "black") or "black").lower()
    if value in {"none", "нет", "transparent"}:
        return "rgba(0,0,0,0)"
    if value in {"white", "белый"}:
        return "white"
    if value in {"group", "series", "цвет группы"}:
        return str((style or {}).get("color", "black"))
    return "black"


def _rgba(color: str, alpha: float) -> str:
    if color.startswith("#") and len(color) == 7:
        r = int(color[1:3], 16)
        g = int(color[3:5], 16)
        b = int(color[5:7], 16)
        return f"rgba({r},{g},{b},{max(0.0, min(1.0, alpha)):.3f})"
    return color


def _manual_polygons(style: Mapping[str, Any]) -> list[np.ndarray]:
    raw = style.get("manual_envelope_points")
    if not isinstance(raw, list) or len(raw) < 3:
        return []
    try:
        polygon = np.asarray(raw, dtype=float)
    except (TypeError, ValueError):
        return []
    if polygon.ndim != 2 or polygon.shape[1] != 2 or not np.isfinite(polygon).all():
        return []
    if not np.allclose(polygon[0], polygon[-1]):
        polygon = np.vstack([polygon, polygon[0]])
    return [polygon]


def _field_dash(value: Any) -> str:
    value = str(value or "solid").lower()
    return value if value in {"solid", "dot", "dash", "longdash", "dashdot", "longdashdot"} else "solid"


def _add_envelope_traces(figure: go.Figure, subset: pd.DataFrame, x: str, y: str, group_name: str, style: Mapping[str, Any]) -> None:
    display_mode = str(style.get("display_mode", "points") or "points")
    if display_mode not in {"field", "points+field", "centroid"}:
        return
    color = str(style.get("color", "#636EFA"))
    if display_mode == "centroid":
        x_values = pd.to_numeric(subset[x], errors="coerce")
        y_values = pd.to_numeric(subset[y], errors="coerce")
        valid = pd.DataFrame({"x": x_values, "y": y_values}).replace([np.inf, -np.inf], np.nan).dropna()
        if valid.empty:
            return
        figure.add_trace(go.Scatter(
            x=[float(valid["x"].median())], y=[float(valid["y"].median())], mode="markers+text",
            text=[str(group_name)], textposition="top center", name=f"{group_name} · центр",
            marker={"size": _marker_size(style) + 3.0, "color": color, "symbol": _marker_symbol(style),
                    "line": {"width": float(style.get("outline_width", 1.0) or 0.0), "color": _outline_color(style)}},
            hovertemplate=f"<b>{group_name}</b><br>медианный центр<extra></extra>", showlegend=False,
        ))
        return
    method = str(style.get("envelope_method", "confidence_ellipse") or "confidence_ellipse")
    level = float(style.get("envelope_level", 0.90) or 0.90)
    polygons = _manual_polygons(style)
    manual = bool(polygons)
    result = None
    if not manual:
        try:
            result = compute_group_envelope(subset, x, y, method=method, level=level)
            polygons = result.polygons
        except (ValueError, np.linalg.LinAlgError):
            return
    fill_alpha = float(style.get("envelope_alpha", 0.16) or 0.0)
    fill_color = str(style.get("envelope_fill_color") or color)
    line_color = str(style.get("envelope_line_color") or color)
    fill_enabled = bool(style.get("envelope_fill", True))
    line_width = float(style.get("envelope_line_width", 1.5) or 0.0)
    line_dash = _field_dash(style.get("envelope_line_dash", "solid"))
    for index, polygon in enumerate(polygons):
        description = f"manual; исходное: {method}, уровень {level:.0%}; n={len(subset)}" if manual else f"{result.method}; уровень {result.level:.0%}; n={result.n}"
        figure.add_trace(go.Scatter(
            x=polygon[:, 0], y=polygon[:, 1], mode="lines", fill="toself" if fill_enabled else None,
            fillcolor=_rgba(fill_color, fill_alpha) if fill_enabled else "rgba(0,0,0,0)",
            line={"color": line_color, "width": line_width, "dash": line_dash},
            name=f"{group_name} · поле" if index == 0 else f"{group_name} · поле {index + 1}",
            legendgroup=f"envelope-{group_name}", showlegend=index == 0,
            hovertemplate=f"<b>{group_name}</b><br>{description}<extra></extra>",
        ))


def build_interactive_scatter(dataframe: pd.DataFrame, x: str, y: str, group_col: str | None = None, *, x_label: str | None = None, y_label: str | None = None, title: str = "", log_x: bool = False, log_y: bool = False, style_map: Mapping[str, Mapping[str, Any]] | None = None) -> go.Figure:
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
        column
        for column in ["Sample", "Point", "Generation", SOURCE_LABEL_COLUMN, WORK_GROUP_COLUMN]
        if column in work.columns
    ]
    if group_col and group_col in work.columns:
        labels = display_group_series(work[group_col])
        groups = [(name, work[labels == name]) for name in labels.unique().tolist()]
    else:
        groups = [("Все точки", work)]
    figure = go.Figure()
    for group_index, (group_name, subset) in enumerate(groups):
        if subset.empty:
            continue
        style = dict((style_map or {}).get(str(group_name), {}))
        style.setdefault("color", default_group_color(group_index))
        _add_envelope_traces(figure, subset, x, y, str(group_name), style)
        display_mode = str(style.get("display_mode", "points") or "points")
        if display_mode in {"field", "centroid"}:
            continue
        customdata = [[str(row["_analysis_id"])] + [_text(row.get(column)) for column in hover_columns] for _, row in subset.iterrows()]
        hover_lines = [f"<b>{x_label or x}</b>: %{{x}}", f"<b>{y_label or y}</b>: %{{y}}"]
        for index, column in enumerate(hover_columns, start=1):
            hover_lines.append(f"<b>{column}</b>: %{{customdata[{index}]}}")
        hover_lines.append("<extra></extra>")
        figure.add_trace(go.Scattergl(
            x=subset[x], y=subset[y], mode="markers", name=str(group_name), customdata=customdata,
            marker={"size": _marker_size(style), "symbol": _marker_symbol(style), "opacity": float(style.get("alpha", 0.9) or 0.9), "color": style["color"],
                    "line": {"width": float(style.get("outline_width", 1.0) or 0.0), "color": _outline_color(style)}},
            hovertemplate="<br>".join(hover_lines), selected={"marker": {"opacity": 1.0, "size": _marker_size(style) + 3.0}}, unselected={"marker": {"opacity": 0.35}},
        ))
    figure.update_layout(title=title or None, xaxis_title=x_label or x, yaxis_title=y_label or y, dragmode="lasso", clickmode="event+select", selectdirection="any", margin={"l": 55, "r": 20, "t": 50 if title else 20, "b": 55}, legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "left", "x": 0}, height=610)
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
