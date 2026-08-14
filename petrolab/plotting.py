from __future__ import annotations

from io import BytesIO, StringIO

import matplotlib.pyplot as plt
import pandas as pd

from petrolab.group_envelopes import compute_group_envelope

MARKERS = ["o", "s", "^", "D", "v", "P", "X", "<", ">", "h", "*", "p", "8"]


def _resolve_style(group_name, idx: int, style_map: dict | None, monochrome: bool = False):
    style_map = style_map or {}
    raw = style_map.get(str(group_name), {}) if group_name is not None else {}
    marker = raw.get("marker") or MARKERS[idx % len(MARKERS)]
    size_multiplier = float(raw.get("size_multiplier", 1.0) or 1.0)
    alpha = float(raw.get("alpha", 0.9) or 0.9)
    filled = bool(raw.get("filled", True))
    base_color = raw.get("color") or "black"
    outline = str(raw.get("outline_color", "black") or "black")
    outline_width = float(raw.get("outline_width", 1.0) or 0.0)
    if monochrome:
        edge_color = "black"
        face_color = "black" if filled else "white"
        field_color = "black"
    else:
        if outline == "white":
            edge_color = "white"
        elif outline in {"group", "series"}:
            edge_color = base_color
        elif outline in {"none", "transparent"}:
            edge_color = "none"
        else:
            edge_color = "black"
        face_color = base_color if filled else "none"
        field_color = base_color
    return {
        "marker": marker,
        "size_multiplier": size_multiplier,
        "alpha": alpha,
        "filled": filled,
        "edgecolors": edge_color,
        "facecolors": face_color,
        "outline_width": outline_width,
        "field_color": field_color,
        "display_mode": str(raw.get("display_mode", "points") or "points"),
        "envelope_method": str(raw.get("envelope_method", "confidence_ellipse") or "confidence_ellipse"),
        "envelope_level": float(raw.get("envelope_level", 0.90) or 0.90),
        "envelope_alpha": float(raw.get("envelope_alpha", 0.16) or 0.16),
        "envelope_line_width": float(raw.get("envelope_line_width", 1.5) or 1.5),
    }


def _draw_group_field(ax, part: pd.DataFrame, x: str, y: str, name, stl: dict) -> None:
    mode = stl["display_mode"]
    if mode == "centroid":
        xv = pd.to_numeric(part[x], errors="coerce")
        yv = pd.to_numeric(part[y], errors="coerce")
        valid = pd.DataFrame({"x": xv, "y": yv}).dropna()
        if not valid.empty:
            ax.scatter(
                [valid["x"].median()], [valid["y"].median()],
                s=90 * stl["size_multiplier"], marker=stl["marker"],
                edgecolors=stl["edgecolors"], facecolors=stl["facecolors"],
                linewidths=stl["outline_width"], zorder=5,
            )
            ax.annotate(str(name), (valid["x"].median(), valid["y"].median()), xytext=(4, 4), textcoords="offset points")
        return
    if mode not in {"field", "points+field"}:
        return
    try:
        result = compute_group_envelope(
            part, x, y,
            method=stl["envelope_method"],
            level=stl["envelope_level"],
        )
    except ValueError:
        return
    for polygon in result.polygons:
        ax.fill(
            polygon[:, 0], polygon[:, 1],
            facecolor=stl["field_color"], edgecolor=stl["field_color"],
            alpha=stl["envelope_alpha"], linewidth=stl["envelope_line_width"], zorder=1,
        )


def build_scatter(
    df: pd.DataFrame,
    x: str,
    y: str,
    group: str | None = None,
    x_label: str | None = None,
    y_label: str | None = None,
    title: str = "",
    marker_size: float = 46,
    xlim: tuple[float | None, float | None] | None = None,
    ylim: tuple[float | None, float | None] | None = None,
    log_x: bool = False,
    log_y: bool = False,
    show_grid: bool = False,
    style_map: dict | None = None,
    monochrome: bool = False,
    show_legend: bool = True,
    annotate: bool = False,
    label_col: str | None = None,
    annotate_top_n: int = 0,
    figure_size: tuple[float, float] = (7.8, 5.8),
    font_family: str = "Arial",
    font_size: float = 10,
    tick_size: float = 9,
    title_size: float | None = None,
    spine_width: float = 1.0,
):
    with plt.rc_context({
        "font.family": font_family,
        "font.size": font_size,
        "axes.labelsize": font_size,
        "xtick.labelsize": tick_size,
        "ytick.labelsize": tick_size,
        "legend.fontsize": tick_size,
    }):
        fig, ax = plt.subplots(figsize=figure_size, constrained_layout=True)
        if group and group in df.columns:
            grouped = list(df.groupby(group, dropna=False, sort=False))
            for i, (name, part) in enumerate(grouped):
                stl = _resolve_style(name, i, style_map, monochrome=monochrome)
                _draw_group_field(ax, part, x, y, name, stl)
                if stl["display_mode"] not in {"field", "centroid"}:
                    ax.scatter(
                        part[x], part[y], s=marker_size * stl["size_multiplier"], label=str(name), alpha=stl["alpha"],
                        marker=stl["marker"], edgecolors=stl["edgecolors"], facecolors=stl["facecolors"],
                        linewidths=stl["outline_width"], zorder=3,
                    )
                elif stl["display_mode"] == "field":
                    # Invisible legend handle preserves group identification without plotting the raw points.
                    ax.plot([], [], color=stl["field_color"], label=str(name), linewidth=max(1.0, stl["envelope_line_width"]))
                if annotate and stl["display_mode"] not in {"field", "centroid"} and label_col and label_col in part.columns:
                    subset = part.head(annotate_top_n) if annotate_top_n else part
                    for _, row in subset.iterrows():
                        text = str(row.get(label_col, "")).strip()
                        if text:
                            ax.annotate(text, (row[x], row[y]), xytext=(4, 4), textcoords="offset points", fontsize=max(7, tick_size - 1))
            if show_legend:
                ax.legend(frameon=False)
        else:
            ax.scatter(df[x], df[y], s=marker_size, alpha=0.9, edgecolors="black", linewidths=0.6, facecolors="black" if monochrome else None)
            if annotate and label_col and label_col in df.columns:
                subset = df.head(annotate_top_n) if annotate_top_n else df
                for _, row in subset.iterrows():
                    text = str(row.get(label_col, "")).strip()
                    if text:
                        ax.annotate(text, (row[x], row[y]), xytext=(4, 4), textcoords="offset points", fontsize=max(7, tick_size - 1))

        ax.set_xlabel(x_label or x)
        ax.set_ylabel(y_label or y)
        if title:
            ax.set_title(title, fontsize=title_size or font_size + 1)
        if xlim and (xlim[0] is not None or xlim[1] is not None):
            ax.set_xlim(left=xlim[0], right=xlim[1])
        if ylim and (ylim[0] is not None or ylim[1] is not None):
            ax.set_ylim(bottom=ylim[0], top=ylim[1])
        if log_x:
            ax.set_xscale("log")
        if log_y:
            ax.set_yscale("log")
        if show_grid:
            ax.grid(True, alpha=0.2)
        ax.tick_params(direction="out", width=spine_width)
        for spine in ax.spines.values():
            spine.set_linewidth(spine_width)
        return fig


def figure_png_bytes(fig, dpi: int = 600) -> bytes:
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight")
    return buf.getvalue()


def figure_svg_bytes(fig) -> bytes:
    buf = StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    return buf.getvalue().encode("utf-8")
