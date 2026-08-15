from __future__ import annotations

import math

import matplotlib.pyplot as plt
import pandas as pd

from petrolab.group_styles import display_group_series
from petrolab.plotting import _draw_group_field, _resolve_style


def _numeric_panel(dataframe: pd.DataFrame, x: str, y: str, log_x: bool, log_y: bool) -> pd.DataFrame:
    work = dataframe.copy()
    work[x] = pd.to_numeric(work[x], errors="coerce")
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna(subset=[x, y])
    if log_x:
        work = work[work[x] > 0]
    if log_y:
        work = work[work[y] > 0]
    return work


def build_multi_panel_scatter(
    dataframe: pd.DataFrame,
    panels: list[dict],
    *,
    group_column: str | None = None,
    style_map: dict | None = None,
    columns: int = 2,
    width_in: float = 7.4,
    panel_height_in: float = 3.6,
    font_family: str = "Arial",
    font_size: float = 9.0,
    tick_size: float = 8.0,
    spine_width: float = 0.9,
    marker_size: float = 48.0,
    show_legend: bool = True,
    grid: bool = False,
):
    """Render several XY views from one immutable selection and one shared style map."""
    valid = [panel for panel in panels if panel.get("x") in dataframe.columns and panel.get("y") in dataframe.columns]
    if not valid:
        raise ValueError("Нет валидных панелей для построения")
    ncols = max(1, min(int(columns), len(valid)))
    nrows = int(math.ceil(len(valid) / ncols))
    with plt.rc_context({
        "font.family": font_family,
        "font.size": font_size,
        "axes.labelsize": font_size,
        "xtick.labelsize": tick_size,
        "ytick.labelsize": tick_size,
        "legend.fontsize": tick_size,
    }):
        fig, axes = plt.subplots(
            nrows,
            ncols,
            figsize=(float(width_in), float(panel_height_in) * nrows),
            squeeze=False,
            constrained_layout=True,
        )
        legend_handles = None
        legend_labels = None
        for index, panel in enumerate(valid):
            ax = axes.flat[index]
            x = str(panel["x"])
            y = str(panel["y"])
            log_x = bool(panel.get("log_x", False))
            log_y = bool(panel.get("log_y", False))
            work = _numeric_panel(dataframe, x, y, log_x, log_y)
            if work.empty:
                ax.text(0.5, 0.5, "Нет валидных точек", ha="center", va="center", transform=ax.transAxes)
            elif group_column and group_column in work.columns:
                labels = display_group_series(work[group_column])
                for group_index, name in enumerate(labels.unique().tolist()):
                    part = work.loc[labels == name]
                    stl = _resolve_style(name, group_index, style_map, monochrome=False)
                    _draw_group_field(ax, part, x, y, name, stl)
                    if stl["display_mode"] not in {"field", "centroid"}:
                        ax.scatter(
                            part[x], part[y],
                            s=float(marker_size) * stl["size_multiplier"],
                            label=str(name), alpha=stl["alpha"], marker=stl["marker"],
                            edgecolors=stl["edgecolors"], facecolors=stl["facecolors"],
                            linewidths=stl["outline_width"], zorder=3,
                        )
                    elif stl["display_mode"] == "field":
                        ax.plot([], [], color=stl["field_line_color"], label=str(name), linewidth=max(1.0, stl["envelope_line_width"]))
                if legend_handles is None:
                    legend_handles, legend_labels = ax.get_legend_handles_labels()
            else:
                ax.scatter(work[x], work[y], s=float(marker_size), alpha=0.9, edgecolors="black", linewidths=0.6)
            ax.set_xlabel(str(panel.get("x_label") or x))
            ax.set_ylabel(str(panel.get("y_label") or y))
            title = str(panel.get("title") or f"{y} vs {x}")
            if title:
                ax.set_title(title)
            if log_x:
                ax.set_xscale("log")
            if log_y:
                ax.set_yscale("log")
            if grid:
                ax.grid(True, alpha=0.18)
            ax.tick_params(direction="out", width=float(spine_width))
            for spine in ax.spines.values():
                spine.set_linewidth(float(spine_width))

        for index in range(len(valid), nrows * ncols):
            axes.flat[index].axis("off")
        if show_legend and legend_handles:
            fig.legend(
                legend_handles,
                legend_labels,
                loc="outside upper center",
                ncol=min(5, max(1, len(legend_labels))),
                frameon=False,
            )
        return fig
