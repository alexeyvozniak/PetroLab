from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd


# Match Plotly's standard qualitative sequence so interactive and publication views use
# the same default visual coding before the user applies a saved style profile.
DEFAULT_GROUP_COLORS: tuple[str, ...] = (
    "#636EFA",
    "#EF553B",
    "#00CC96",
    "#AB63FA",
    "#FFA15A",
    "#19D3F3",
    "#FF6692",
    "#B6E880",
    "#FF97FF",
    "#FECB52",
)


def display_group_series(series: pd.Series) -> pd.Series:
    """Return stable legend labels shared by Plotly and Matplotlib."""
    return series.astype("string").fillna("Без группы").replace("", "Без группы")


def resolved_group_styles(
    group_names: Sequence[str],
    style_map: Mapping[str, Mapping[str, object]] | None,
) -> dict[str, dict[str, object]]:
    """Fill missing group colors deterministically without overriding user styles."""
    incoming = style_map or {}
    resolved: dict[str, dict[str, object]] = {}
    for index, raw_name in enumerate(group_names):
        name = str(raw_name)
        style = dict(incoming.get(name, {}))
        style.setdefault("color", DEFAULT_GROUP_COLORS[index % len(DEFAULT_GROUP_COLORS)])
        resolved[name] = style
    return resolved
