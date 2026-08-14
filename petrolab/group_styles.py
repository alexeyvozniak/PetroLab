from __future__ import annotations

from collections.abc import Mapping, Sequence

import pandas as pd

DEFAULT_GROUP_COLORS: tuple[str, ...] = (
    "#636EFA", "#EF553B", "#00CC96", "#AB63FA", "#FFA15A",
    "#19D3F3", "#FF6692", "#B6E880", "#FF97FF", "#FECB52",
)
MISSING_GROUP_LABEL = "Без группы"


def display_group_series(series: pd.Series) -> pd.Series:
    return series.astype("string").fillna(MISSING_GROUP_LABEL).replace("", MISSING_GROUP_LABEL)


def default_group_color(index: int) -> str:
    return DEFAULT_GROUP_COLORS[int(index) % len(DEFAULT_GROUP_COLORS)]


def resolved_group_styles(group_names: Sequence[str], style_map: Mapping[str, Mapping[str, object]] | None = None) -> dict[str, dict[str, object]]:
    incoming = style_map or {}
    resolved: dict[str, dict[str, object]] = {}
    for index, raw_name in enumerate(group_names):
        name = str(raw_name)
        style = dict(incoming.get(name, {}))
        style.setdefault("color", default_group_color(index))
        resolved[name] = style
    return resolved
