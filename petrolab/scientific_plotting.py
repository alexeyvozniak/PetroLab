from __future__ import annotations

import matplotlib.patches as patches
import matplotlib.pyplot as plt
import pandas as pd

from petrolab.plot_text import matplotlib_label
from petrolab.scientific_overlays import draw_xy_overlay
from petrolab.visualization_presets import POINT_STYLE_PRESETS


def build_scientific_xy_figure(
    dataframe: pd.DataFrame,
    *,
    x: str,
    y: str,
    x_label: str,
    y_label: str,
    title: str = "",
    group_column: str | None = None,
    point_style_name: str = "balanced",
    font_family: str = "Arial",
    font_size: float = 9.0,
    tick_size: float = 8.0,
    label_size: float = 9.0,
    marker_size: float = 55.0,
    line_width: float = 0.9,
    spine_width: float = 0.9,
    figure_size: tuple[float, float] = (7.2, 5.4),
    grid: bool = False,
    monochrome: bool = False,
    show_legend: bool = True,
    point_label_column: str | None = None,
    overlay_id: str | None = None,
    custom_fields: pd.DataFrame | None = None,
):
    work = dataframe.copy()
    work[x] = pd.to_numeric(work[x], errors="coerce")
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna(subset=[x, y])
    point_style = POINT_STYLE_PRESETS[point_style_name]

    with plt.rc_context({"font.family": font_family, "font.size": font_size}):
        fig, ax = plt.subplots(figsize=figure_size)
        if group_column and group_column in work.columns:
            groups = list(work.groupby(group_column, dropna=False, sort=False))
        else:
            groups = [("Все точки", work)]

        for index, (group_name, subset) in enumerate(groups):
            marker = point_style.markers[index % len(point_style.markers)]
            face = "none" if (not point_style.filled or monochrome) else None
            kwargs: dict[str, object] = {
                "marker": marker,
                "s": marker_size * point_style.size_multiplier,
                "alpha": point_style.alpha,
                "linewidths": 0.8,
                "label": str(group_name),
            }
            if face == "none":
                kwargs["facecolors"] = "none"
            ax.scatter(subset[x], subset[y], **kwargs)

        overlay = draw_xy_overlay(ax, overlay_id)
        if custom_fields is not None and not custom_fields.empty:
            for _, row in custom_fields.iterrows():
                try:
                    x_min, x_max = float(row["x_min"]), float(row["x_max"])
                    y_min, y_max = float(row["y_min"]), float(row["y_max"])
                except (TypeError, ValueError, KeyError):
                    continue
                if x_min >= x_max or y_min >= y_max:
                    continue
                rect = patches.Rectangle(
                    (x_min, y_min), x_max - x_min, y_max - y_min,
                    fill=False, linewidth=line_width, linestyle="--", alpha=0.7,
                )
                ax.add_patch(rect)
                label = str(row.get("label", "")).strip()
                if label:
                    ax.text(
                        (x_min + x_max) / 2.0,
                        (y_min + y_max) / 2.0,
                        matplotlib_label(label),
                        ha="center",
                        va="center",
                        fontsize=max(6, font_size - 1),
                    )

        if point_label_column and point_label_column in work.columns:
            for _, row in work.iterrows():
                text = str(row.get(point_label_column, "")).strip()
                if text and text.lower() != "nan":
                    ax.annotate(
                        text,
                        (row[x], row[y]),
                        xytext=(3, 3),
                        textcoords="offset points",
                        fontsize=max(6, font_size - 1),
                    )

        ax.set_xlabel(matplotlib_label(x_label or x), fontsize=label_size)
        ax.set_ylabel(matplotlib_label(y_label or y), fontsize=label_size)
        ax.tick_params(labelsize=tick_size)
        ax.set_title(matplotlib_label(title))
        for spine in ax.spines.values():
            spine.set_linewidth(spine_width)
        if grid:
            ax.grid(True, alpha=0.22)
        if show_legend and (len(groups) > 1 or overlay is not None):
            ax.legend(frameon=False, fontsize=max(6, font_size - 1), loc="best")
        fig.tight_layout()
        return fig
