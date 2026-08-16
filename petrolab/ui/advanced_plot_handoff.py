from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

from petrolab.ui.plot_spec import PlotSpec


def _unique_analysis_ids(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(value).strip()
            for value in values
            if str(value).strip()
        )
    )


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
    universe_analysis_ids: Iterable[Any] | None = None,
) -> PlotSpec:
    """Translate the advanced editor's graph into the shared PlotSpec.

    ``analysis_ids`` describe the graph's scientific DataUniverse, not only the rows
    currently visible after source/series/log/outlier presentation filters. When an
    explicit universe is supplied it is preserved verbatim (deduplicated); this lets
    hidden sources or temporarily excluded points return when the corresponding
    presentation control is changed. Legacy callers without an explicit universe
    retain the previous visible-row behavior for compatibility.
    """
    if universe_analysis_ids is not None:
        analysis_ids = _unique_analysis_ids(universe_analysis_ids)
    elif "_analysis_id" in plot_dataframe.columns:
        analysis_ids = _unique_analysis_ids(plot_dataframe["_analysis_id"].tolist())
    else:
        analysis_ids = ()

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
