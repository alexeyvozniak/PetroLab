from __future__ import annotations

from io import BytesIO, StringIO

import matplotlib.pyplot as plt
import pandas as pd

MARKERS = ["o", "s", "^", "D", "v", "P", "X", "<", ">", "h", "*", "p", "8"]


def _resolve_style(group_name, idx: int, style_map: dict | None, monochrome: bool = False):
    style_map = style_map or {}
    raw = style_map.get(str(group_name), {}) if group_name is not None else {}
    marker = raw.get("marker") or MARKERS[idx % len(MARKERS)]
    size_multiplier = float(raw.get("size_multiplier", 1.0) or 1.0)
    alpha = float(raw.get("alpha", 0.9) or 0.9)
    filled = bool(raw.get("filled", True))
    base_color = raw.get("color")
    edge_color = raw.get("edge_color")
    face_color = raw.get("face_color")
    if monochrome:
        edge_color = "black"
        face_color = "black" if filled else "white"
    else:
        if face_color is None:
            face_color = base_color if filled else "none"
        if edge_color is None:
            edge_color = "black" if filled else base_color
    return {
        "marker": marker,
        "size_multiplier": size_multiplier,
        "alpha": alpha,
        "filled": filled,
        "edgecolors": edge_color,
        "facecolors": face_color if face_color is not None else ("black" if filled else "none"),
    }


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
                ax.scatter(
                    part[x], part[y], s=marker_size * stl["size_multiplier"], label=str(name), alpha=stl["alpha"],
                    marker=stl["marker"], edgecolors=stl["edgecolors"], facecolors=stl["facecolors"], linewidths=0.8,
                )
                if annotate and label_col and label_col in part.columns:
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
