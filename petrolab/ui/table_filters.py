from __future__ import annotations

import pandas as pd


FILTER_MODES = ("Оставить", "Скрыть")


def normalize_filter_mode(value: object) -> str:
    mode = str(value or "Оставить")
    return mode if mode in FILTER_MODES else "Оставить"


def apply_categorical_filter(
    dataframe: pd.DataFrame,
    column: str,
    values: list[str] | tuple[str, ...],
    *,
    mode: str = "Оставить",
) -> pd.DataFrame:
    """Filter the current presentation without mutating source rows or selection."""
    if dataframe.empty or column not in dataframe.columns or not values:
        return dataframe.copy()
    wanted = {str(value) for value in values}
    matches = dataframe[column].astype(str).isin(wanted)
    normalized = normalize_filter_mode(mode)
    mask = matches if normalized == "Оставить" else ~matches
    return dataframe.loc[mask].copy()
