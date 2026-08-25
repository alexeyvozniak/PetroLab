from __future__ import annotations

"""Plotly-compatible wrapper for the reference linked-view workspace.

Scattergl selected.marker does not accept marker.line in Plotly 6. Keep the
reference selection emphasis using supported size/opacity properties while the
ordinary marker retains its thin outline.
"""

import pandas as pd
import plotly.graph_objects as go

from . import linked_views_reference as _reference


def _scatter_compatible(
    frame: pd.DataFrame,
    x: str,
    y: str,
    *,
    title: str,
    color_by: str | None,
    symbol_by: str | None,
    active: set[str],
    dragmode: str,
) -> go.Figure:
    work = frame.copy()
    work[x] = pd.to_numeric(work[x], errors="coerce")
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna(subset=[x, y])
    color_values = work[color_by].fillna("Без значения").astype(str) if color_by else pd.Series("Все", index=work.index)
    symbol_values = work[symbol_by].fillna("Без значения").astype(str) if symbol_by else pd.Series("Все", index=work.index)
    color_map = {
        value: _reference._COLORS[index % len(_reference._COLORS)]
        for index, value in enumerate(color_values.drop_duplicates())
    }
    symbol_map = {
        value: _reference._SYMBOLS[index % len(_reference._SYMBOLS)]
        for index, value in enumerate(symbol_values.drop_duplicates())
    }

    figure = go.Figure()
    for color_value in color_values.drop_duplicates():
        for symbol_value in symbol_values.drop_duplicates():
            subset = work[(color_values == color_value) & (symbol_values == symbol_value)]
            if subset.empty:
                continue
            custom = [
                [str(row["_analysis_id"]), _reference._point_label(row)]
                for _, row in subset.iterrows()
            ]
            selected = [index for index, item in enumerate(custom) if str(item[0]) in active]
            figure.add_trace(
                go.Scattergl(
                    x=subset[x],
                    y=subset[y],
                    mode="markers",
                    customdata=custom,
                    name=str(color_value) if not symbol_by else f"{color_value} · {symbol_value}",
                    selectedpoints=selected if active else None,
                    marker={
                        "color": color_map[str(color_value)],
                        "symbol": symbol_map[str(symbol_value)],
                        "size": 8,
                        "opacity": 0.86 if not active else 0.32,
                        "line": {"width": 0.7, "color": "#ffffff"},
                    },
                    selected={"marker": {"size": 11, "opacity": 1.0}},
                    unselected={"marker": {"opacity": 0.14}},
                    hovertemplate=(
                        f"<b>{x}</b>: %{{x:.5g}}<br><b>{y}</b>: %{{y:.5g}}"
                        "<br>%{customdata[1]}<extra></extra>"
                    ),
                )
            )
    figure.update_layout(
        height=330,
        margin={"l": 48, "r": 12, "t": 42, "b": 42},
        title={"text": title, "font": {"size": 14}},
        xaxis_title=x,
        yaxis_title=y,
        dragmode=dragmode,
        clickmode="event+select",
        showlegend=False,
        paper_bgcolor="#ffffff",
        plot_bgcolor="#ffffff",
        font={"color": "#26364a", "size": 11},
    )
    figure.update_xaxes(gridcolor="#e7ecef", zeroline=False)
    figure.update_yaxes(gridcolor="#e7ecef", zeroline=False)
    return figure


def render_linked_views_reference_page() -> None:
    original = _reference._scatter
    _reference._scatter = _scatter_compatible
    try:
        _reference.render_linked_views_reference_page()
    finally:
        _reference._scatter = original
