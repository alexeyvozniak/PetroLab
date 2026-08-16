from __future__ import annotations

import math
from typing import Iterable

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from petrolab.group_styles import display_group_series
from petrolab.plotting import _draw_group_field, _resolve_style
from petrolab.publication_composer import apply_panel_label


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


def _padded_limits(values: pd.Series, *, log: bool) -> tuple[float, float] | None:
    numeric = pd.to_numeric(values, errors="coerce").dropna().astype(float)
    if log:
        numeric = numeric[numeric > 0]
    if numeric.empty:
        return None
    lower = float(numeric.min())
    upper = float(numeric.max())
    if lower == upper:
        if log:
            factor = 1.15
            return lower / factor, upper * factor
        pad = max(abs(lower) * 0.05, 0.5)
        return lower - pad, upper + pad
    if log:
        log_lower = math.log10(lower)
        log_upper = math.log10(upper)
        pad = max((log_upper - log_lower) * 0.045, 0.015)
        return 10 ** (log_lower - pad), 10 ** (log_upper + pad)
    pad = (upper - lower) * 0.045
    return lower - pad, upper + pad


def _manual_axis_range(panel: dict, axis: str) -> tuple[float, float] | None:
    try:
        lower = float(panel.get(f"{axis}_min"))
        upper = float(panel.get(f"{axis}_max"))
    except (TypeError, ValueError):
        return None
    if not (math.isfinite(lower) and math.isfinite(upper) and lower < upper):
        return None
    if bool(panel.get(f"log_{axis}", False)) and lower <= 0:
        return None
    return lower, upper


def apply_manual_panel_limits(
    panels: list[dict],
    limits: list[dict[str, tuple[float, float] | None]],
) -> list[dict[str, tuple[float, float] | None]]:
    """Override automatic limits only for axes with an explicit valid pair."""
    result: list[dict[str, tuple[float, float] | None]] = []
    for index, panel in enumerate(panels):
        base = limits[index] if index < len(limits) and isinstance(limits[index], dict) else {}
        item = {"x": base.get("x"), "y": base.get("y")}
        for axis in ("x", "y"):
            manual = _manual_axis_range(panel, axis)
            if manual is not None:
                item[axis] = manual
        result.append(item)
    return result


def _shared_axes_for_mode(mode: str) -> tuple[str, ...]:
    normalized = str(mode or "independent").casefold()
    if normalized == "shared_x":
        return ("x",)
    if normalized == "shared_y":
        return ("y",)
    if normalized == "shared":
        return ("x", "y")
    return ()


def panel_axis_limits(
    dataframe: pd.DataFrame,
    panels: list[dict],
    *,
    mode: str = "independent",
    focus_ids: Iterable[str] = (),
    id_column: str = "_analysis_id",
) -> list[dict[str, tuple[float, float] | None]]:
    """Resolve automatic panel ranges, then layer explicit panel overrides.

    Modes:
    - ``independent``: plotting-library autoscale unless that panel has explicit
      X/Y min+max.
    - ``shared_x``: same-variable X axes use one range; Y stays automatic.
    - ``shared_y``: same-variable Y axes use one range; X stays automatic.
    - ``shared``: same scientific variables are synchronized wherever they occur
      on X or Y, preserving the previous combined behavior.
    - ``focus``: zoom each panel to the current analysis selection while keeping
      all rows plotted; explicit panel ranges still win.

    Different variables are never forced to the same numeric range. Manual C5
    limits remain the highest-priority viewport override in every mode.
    """
    result = [{"x": None, "y": None} for _ in panels]
    normalized = str(mode or "independent").casefold()
    shared_axes = _shared_axes_for_mode(normalized)
    if normalized not in {"shared", "shared_x", "shared_y", "focus"} or dataframe.empty:
        return apply_manual_panel_limits(panels, result)

    focus = tuple(dict.fromkeys(str(value) for value in focus_ids if str(value)))
    scope = dataframe
    if normalized == "focus":
        if not focus or id_column not in dataframe.columns:
            return apply_manual_panel_limits(panels, result)
        wanted = set(focus)
        scope = dataframe.loc[dataframe[id_column].astype(str).isin(wanted)].copy()
        if scope.empty:
            return apply_manual_panel_limits(panels, result)

    if shared_axes:
        # Combined `shared` retains the earlier cross-axis behavior for the same
        # variable. X-only / Y-only intentionally affect only their named axis.
        cross_axis = normalized == "shared"
        cache: dict[tuple[str, bool] | tuple[str, str, bool], tuple[float, float] | None] = {}
        for panel in panels:
            for axis in shared_axes:
                log_key = f"log_{axis}"
                variable = str(panel.get(axis) or "")
                if not variable or variable not in scope.columns:
                    continue
                log_value = bool(panel.get(log_key, False))
                key = (variable, log_value) if cross_axis else (axis, variable, log_value)
                if key not in cache:
                    cache[key] = _padded_limits(scope[variable], log=log_value)
        for index, panel in enumerate(panels):
            for axis in shared_axes:
                log_key = f"log_{axis}"
                variable = str(panel.get(axis) or "")
                log_value = bool(panel.get(log_key, False))
                key = (variable, log_value) if cross_axis else (axis, variable, log_value)
                result[index][axis] = cache.get(key)
        return apply_manual_panel_limits(panels, result)

    for index, panel in enumerate(panels):
        x = str(panel.get("x") or "")
        y = str(panel.get("y") or "")
        if x not in scope.columns or y not in scope.columns:
            continue
        log_x = bool(panel.get("log_x", False))
        log_y = bool(panel.get("log_y", False))
        work = _numeric_panel(scope, x, y, log_x, log_y)
        if work.empty:
            continue
        result[index]["x"] = _padded_limits(work[x], log=log_x)
        result[index]["y"] = _padded_limits(work[y], log=log_y)
    return apply_manual_panel_limits(panels, result)


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
    axis_limits: list[dict[str, tuple[float, float] | None]] | None = None,
):
    """Render several XY views from one immutable selection and one shared style map."""
    valid = [panel for panel in panels if panel.get("x") in dataframe.columns and panel.get("y") in dataframe.columns]
    if not valid:
        raise ValueError("Нет валидных панелей для построения")
    limits = axis_limits or [{"x": None, "y": None} for _ in valid]
    if len(limits) < len(valid):
        limits = [*limits, *({"x": None, "y": None} for _ in range(len(valid) - len(limits)))]
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
            panel_limits = limits[index] if index < len(limits) else {}
            xlim = panel_limits.get("x") if isinstance(panel_limits, dict) else None
            ylim = panel_limits.get("y") if isinstance(panel_limits, dict) else None
            if xlim is not None and np.isfinite(xlim).all() and xlim[0] < xlim[1]:
                ax.set_xlim(xlim)
            if ylim is not None and np.isfinite(ylim).all() and ylim[0] < ylim[1]:
                ax.set_ylim(ylim)
            if grid:
                ax.grid(True, alpha=0.18)
            ax.tick_params(direction="out", width=float(spine_width))
            for spine in ax.spines.values():
                spine.set_linewidth(float(spine_width))
            apply_panel_label(ax, panel.get("panel_label"))

        for index in range(len(valid), nrows * ncols):
            axes.flat[index].axis("off")
        if show_legend and legend_handles:
            fig.legend(
                legend_handles,
                legend_labels,
                loc="upper center",
                bbox_to_anchor=(0.5, 1.01),
                ncol=min(5, max(1, len(legend_labels))),
                frameon=False,
            )
        return fig