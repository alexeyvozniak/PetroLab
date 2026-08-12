from __future__ import annotations

from math import sqrt

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from matplotlib.figure import Figure

from petrolab.ternary_data import (
    TERNARY_A,
    TERNARY_B,
    TERNARY_C,
    TERNARY_X,
    TERNARY_Y,
    ternary_to_cartesian,
)
from petrolab.ternary_overlays import TernaryOverlay

_PLOTLY_SYMBOLS = {
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


def _group_frames(dataframe: pd.DataFrame, group_col: str | None):
    if group_col and group_col in dataframe.columns:
        values = dataframe[group_col].fillna("—").astype(str)
        for name in values.drop_duplicates().tolist():
            yield name, dataframe.loc[values == name]
    else:
        yield "Все точки", dataframe


def _add_plotly_overlay(figure: go.Figure, overlay: TernaryOverlay) -> None:
    for line in overlay.lines:
        figure.add_trace(
            go.Scatterternary(
                a=[point.a for point in line.points],
                b=[point.b for point in line.points],
                c=[point.c for point in line.points],
                mode="lines",
                line={"width": line.width, "color": "rgba(80,80,80,0.75)"},
                hoverinfo="skip",
                showlegend=False,
                name="classification boundary",
            )
        )
    if overlay.labels:
        figure.add_trace(
            go.Scatterternary(
                a=[label.position.a for label in overlay.labels],
                b=[label.position.b for label in overlay.labels],
                c=[label.position.c for label in overlay.labels],
                mode="text",
                text=[label.text for label in overlay.labels],
                textfont={"size": 11, "color": "rgba(50,50,50,0.9)"},
                hoverinfo="skip",
                showlegend=False,
                name="classification labels",
            )
        )


def build_interactive_ternary(
    dataframe: pd.DataFrame,
    *,
    a_label: str,
    b_label: str,
    c_label: str,
    group_col: str | None = None,
    title: str = "",
    style_map: dict | None = None,
    overlay: TernaryOverlay | None = None,
) -> go.Figure:
    """Build a Plotly diagnostic ternary plot keyed by immutable analysis IDs."""
    style_map = style_map or {}
    figure = go.Figure()
    if overlay is not None:
        _add_plotly_overlay(figure, overlay)

    hover_fields = [
        column
        for column in [
            "Sample",
            "Grain",
            "Point",
            "Generation",
            "Классификационное поле",
        ]
        if column in dataframe.columns
    ]

    for group_name, frame in _group_frames(dataframe, group_col):
        style = style_map.get(str(group_name), {})
        custom_columns = ["_analysis_id", *hover_fields]
        customdata = frame[custom_columns].astype(object).where(frame[custom_columns].notna(), "").to_numpy()
        hover_parts = [
            f"{a_label}: %{{a:.4g}}",
            f"{b_label}: %{{b:.4g}}",
            f"{c_label}: %{{c:.4g}}",
        ]
        for index, field in enumerate(hover_fields, start=1):
            hover_parts.append(f"{field}: %{{customdata[{index}]}}")
        hover_parts.append("ID: %{customdata[0]}")
        marker = {
            "size": max(5.0, 8.0 * float(style.get("size_multiplier", 1.0) or 1.0)),
            "opacity": float(style.get("alpha", 0.9) or 0.9),
            "symbol": _PLOTLY_SYMBOLS.get(str(style.get("marker", "o")), "circle"),
        }
        figure.add_trace(
            go.Scatterternary(
                a=frame[TERNARY_A],
                b=frame[TERNARY_B],
                c=frame[TERNARY_C],
                mode="markers",
                name=str(group_name),
                ids=frame["_analysis_id"].astype(str),
                customdata=customdata,
                marker=marker,
                hovertemplate="<br>".join(hover_parts) + "<extra>%{fullData.name}</extra>",
            )
        )

    figure.update_layout(
        title=title or None,
        ternary={
            "sum": 100,
            "aaxis": {"title": {"text": a_label}, "min": 0},
            "baxis": {"title": {"text": b_label}, "min": 0},
            "caxis": {"title": {"text": c_label}, "min": 0},
        },
        margin={"l": 40, "r": 40, "t": 70 if title else 30, "b": 35},
        legend={"orientation": "h", "y": -0.12},
    )
    return figure


def _draw_ternary_grid(ax, step: int = 20) -> None:
    height = sqrt(3.0) / 2.0
    ax.plot([0, 1, 0.5, 0], [0, 0, height, 0], linewidth=1.0)
    for percent in range(step, 100, step):
        fraction = percent / 100.0
        y = height * fraction
        ax.plot([0.5 * fraction, 1 - 0.5 * fraction], [y, y], linewidth=0.4, alpha=0.35)
        ax.plot(
            [1 - fraction, 0.5 * (1 - fraction)],
            [0, height * (1 - fraction)],
            linewidth=0.4,
            alpha=0.35,
        )
        ax.plot(
            [fraction, 0.5 + 0.5 * fraction],
            [0, height * (1 - fraction)],
            linewidth=0.4,
            alpha=0.35,
        )


def _draw_matplotlib_overlay(ax, overlay: TernaryOverlay, font_size: float) -> None:
    for line in overlay.lines:
        x, y = ternary_to_cartesian(
            [point.a for point in line.points],
            [point.b for point in line.points],
            [point.c for point in line.points],
        )
        ax.plot(x, y, linewidth=line.width, linestyle=line.style, alpha=0.8)
    for label in overlay.labels:
        x, y = ternary_to_cartesian(
            [label.position.a],
            [label.position.b],
            [label.position.c],
        )
        ax.text(
            float(x[0]),
            float(y[0]),
            label.text,
            ha="center",
            va="center",
            fontsize=max(font_size - 1.5, 6.0),
        )


def build_publication_ternary(
    dataframe: pd.DataFrame,
    *,
    a_label: str,
    b_label: str,
    c_label: str,
    group_col: str | None = None,
    title: str = "",
    marker_size: float = 48.0,
    style_map: dict | None = None,
    show_grid: bool = True,
    show_legend: bool = True,
    annotate: bool = False,
    label_col: str | None = None,
    annotate_top_n: int = 25,
    figure_size: tuple[float, float] = (7.0, 6.2),
    font_size: float = 10.0,
    title_size: float = 11.0,
    overlay: TernaryOverlay | None = None,
) -> Figure:
    """Build an editable Matplotlib ternary figure for PNG/SVG publication export."""
    style_map = style_map or {}
    figure, ax = plt.subplots(figsize=figure_size)
    height = sqrt(3.0) / 2.0
    if show_grid:
        _draw_ternary_grid(ax)
    else:
        ax.plot([0, 1, 0.5, 0], [0, 0, height, 0], linewidth=1.0)

    if overlay is not None:
        _draw_matplotlib_overlay(ax, overlay, font_size)

    for group_name, frame in _group_frames(dataframe, group_col):
        style = style_map.get(str(group_name), {})
        marker = str(style.get("marker", "o"))
        size = marker_size * float(style.get("size_multiplier", 1.0) or 1.0)
        alpha = float(style.get("alpha", 0.9) or 0.9)
        filled = bool(style.get("filled", True))
        scatter_kwargs = {
            "s": size,
            "marker": marker,
            "alpha": alpha,
            "label": str(group_name),
            "linewidths": 0.8,
        }
        if not filled:
            scatter_kwargs["facecolors"] = "none"
        ax.scatter(frame[TERNARY_X], frame[TERNARY_Y], **scatter_kwargs)

    ax.text(-0.03, -0.025, a_label, ha="right", va="top", fontsize=font_size)
    ax.text(1.03, -0.025, b_label, ha="left", va="top", fontsize=font_size)
    ax.text(0.5, height + 0.035, c_label, ha="center", va="bottom", fontsize=font_size)

    if annotate and label_col and label_col in dataframe.columns:
        for _, row in dataframe.head(max(int(annotate_top_n), 0)).iterrows():
            value = row.get(label_col)
            if pd.isna(value):
                continue
            ax.annotate(
                str(value),
                (float(row[TERNARY_X]), float(row[TERNARY_Y])),
                xytext=(3, 3),
                textcoords="offset points",
                fontsize=max(font_size - 1.0, 6.0),
            )

    if title:
        ax.set_title(title, fontsize=title_size)
    if show_legend and (group_col and group_col in dataframe.columns):
        ax.legend(
            frameon=False,
            fontsize=max(font_size - 1.0, 6.0),
            bbox_to_anchor=(1.02, 1),
            loc="upper left",
        )

    ax.set_aspect("equal", adjustable="box")
    ax.set_xlim(-0.08, 1.08)
    ax.set_ylim(-0.08, height + 0.09)
    ax.axis("off")
    figure.tight_layout()
    return figure
