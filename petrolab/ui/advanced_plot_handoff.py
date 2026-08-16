from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from petrolab.ui.plot_spec import PlotSpec


def advanced_plot_spec(
    plot_dataframe: pd.DataFrame,
    *,
    dataset_ids: Iterable[int],
    x: str,
    y: str,
    group_column: str | None,
    visible_sources: Iterable[str],
    hidden_sources: Iterable[str],
    journal_preset: str,
    appearance: Mapping[str, Any],
    styles: Mapping[str, Mapping[str, Any]],
) -> PlotSpec:
    """Translate the advanced editor's current graph into the shared PlotSpec.

    This captures only the rows actually admitted to the graph after source,
    range, outlier and log-axis checks. Recipe-only controls remain in the saved
    advanced recipe; the PlotSpec is the portable scientific graph object used
    for linked/multi-panel handoff.
    """
    analysis_ids: tuple[str, ...] = ()
    if "_analysis_id" in plot_dataframe.columns:
        analysis_ids = tuple(
            dict.fromkeys(
                str(value).strip()
                for value in plot_dataframe["_analysis_id"].tolist()
                if str(value).strip()
            )
        )
    visible_series = tuple(str(value) for value in styles if str(value)) if group_column else ()
    return PlotSpec(
        dataset_ids=tuple(dict.fromkeys(int(value) for value in dataset_ids)),
        analysis_ids=analysis_ids,
        x=str(x),
        y=str(y),
        group_column=str(group_column or ""),
        x_label=str(appearance.get("x_label") or x),
        y_label=str(appearance.get("y_label") or y),
        title=str(appearance.get("title") or ""),
        log_x=bool(appearance.get("log_x", False)),
        log_y=bool(appearance.get("log_y", False)),
        visible_sources=tuple(str(value) for value in visible_sources if str(value)),
        hidden_sources=tuple(str(value) for value in hidden_sources if str(value)),
        visible_series=visible_series,
        style_map={str(key): dict(value) for key, value in styles.items()},
        marker_size=float(appearance.get("marker_size", 0.0) or 0.0),
        figure_preset=str(journal_preset or ""),
        show_grid=bool(appearance.get("show_grid", False)),
    )
