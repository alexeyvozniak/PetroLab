from __future__ import annotations

from collections.abc import Iterable

import pandas as pd


EMPTY_GROUP_LABEL = "Без значения"


def group_labels(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(EMPTY_GROUP_LABEL, index=dataframe.index, dtype="string")
    return dataframe[column].astype("string").fillna(EMPTY_GROUP_LABEL).replace("", EMPTY_GROUP_LABEL)


def group_counts(dataframe: pd.DataFrame, column: str) -> list[tuple[str, int]]:
    labels = group_labels(dataframe, column)
    order = labels.drop_duplicates().astype(str).tolist()
    counts = labels.value_counts(dropna=False).to_dict()
    return [(name, int(counts.get(name, 0))) for name in order]


def apply_collapsed_groups(
    dataframe: pd.DataFrame,
    column: str,
    collapsed_groups: Iterable[object] = (),
) -> tuple[pd.DataFrame, list[tuple[str, int]]]:
    """Hide collapsed group rows from the grid while keeping a readable summary.

    This is presentation-only. No analysis IDs, Selection, Work Group or
    Generation are mutated; expanding the group returns the same source rows.
    """
    collapsed = {str(value) for value in collapsed_groups if str(value)}
    if dataframe.empty or column not in dataframe.columns or not collapsed:
        return dataframe.copy(), []
    labels = group_labels(dataframe, column)
    counts = labels.value_counts(dropna=False).to_dict()
    summary = [(name, int(counts.get(name, 0))) for name in labels.drop_duplicates().astype(str) if name in collapsed]
    visible = dataframe.loc[~labels.astype(str).isin(collapsed)].copy()
    return visible, summary


def collapsed_summary_text(summary: list[tuple[str, int]], *, limit: int = 5) -> str:
    if not summary:
        return ""
    shown = [f"{name} · {count}" for name, count in summary[: max(1, int(limit))]]
    hidden = len(summary) - len(shown)
    suffix = f" · ещё {hidden}" if hidden > 0 else ""
    return "Свернуто: " + "; ".join(shown) + suffix
