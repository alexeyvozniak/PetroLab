from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class OutlierResult:
    keep_mask: pd.Series
    outlier_mask: pd.Series
    method: str
    columns: tuple[str, ...]
    threshold: float

    @property
    def outlier_count(self) -> int:
        return int(self.outlier_mask.sum())


def apply_numeric_ranges(
    dataframe: pd.DataFrame,
    ranges: Mapping[str, tuple[float | None, float | None]],
) -> pd.DataFrame:
    """Apply user-defined numeric ranges without modifying the source dataframe."""
    result = dataframe
    for column, bounds in ranges.items():
        if column not in result.columns:
            continue
        low, high = bounds
        values = pd.to_numeric(result[column], errors="coerce")
        mask = values.notna()
        if low is not None:
            mask &= values >= float(low)
        if high is not None:
            mask &= values <= float(high)
        result = result.loc[mask]
    return result


def robust_outliers(
    dataframe: pd.DataFrame,
    columns: list[str] | tuple[str, ...],
    *,
    method: str = "MAD",
    threshold: float = 3.5,
) -> OutlierResult:
    """Flag rows that are robust outliers in any selected column.

    MAD uses modified z-scores: 0.67448975 * |x - median| / MAD.
    IQR uses Tukey fences with the supplied multiplier (normally 1.5 or 3.0).
    Missing values are not automatically called outliers; they are handled separately
    by the plotting layer when required X/Y values are dropped.
    """
    selected = tuple(column for column in columns if column in dataframe.columns)
    outlier = pd.Series(False, index=dataframe.index, dtype=bool)
    method_key = str(method).strip().upper()

    if not selected:
        return OutlierResult(~outlier, outlier, method_key, selected, float(threshold))

    for column in selected:
        values = pd.to_numeric(dataframe[column], errors="coerce")
        finite = values[np.isfinite(values)]
        if len(finite) < 4:
            continue

        if method_key == "MAD":
            median = float(finite.median())
            mad = float((finite - median).abs().median())
            if not np.isfinite(mad) or mad <= 0:
                continue
            score = 0.6744897501960817 * (values - median).abs() / mad
            outlier |= score > float(threshold)
        elif method_key == "IQR":
            q1 = float(finite.quantile(0.25))
            q3 = float(finite.quantile(0.75))
            iqr = q3 - q1
            if not np.isfinite(iqr) or iqr <= 0:
                continue
            low = q1 - float(threshold) * iqr
            high = q3 + float(threshold) * iqr
            outlier |= (values < low) | (values > high)
        else:
            raise ValueError("Неизвестный метод выбросов. Поддерживаются MAD и IQR.")

    return OutlierResult(~outlier, outlier, method_key, selected, float(threshold))


def exclude_analysis_ids(dataframe: pd.DataFrame, analysis_ids: list[str] | tuple[str, ...]) -> pd.DataFrame:
    """Return a view without explicitly excluded analysis IDs; source data are untouched."""
    if "_analysis_id" not in dataframe.columns or not analysis_ids:
        return dataframe
    excluded = {str(value) for value in analysis_ids}
    return dataframe.loc[~dataframe["_analysis_id"].astype(str).isin(excluded)]
