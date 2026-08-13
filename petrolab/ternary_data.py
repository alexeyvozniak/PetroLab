from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np
import pandas as pd

TERNARY_A = "_ternary_a"
TERNARY_B = "_ternary_b"
TERNARY_C = "_ternary_c"
TERNARY_SUM = "_ternary_sum"
TERNARY_REASON = "_ternary_reason"
TERNARY_X = "_ternary_x"
TERNARY_Y = "_ternary_y"


@dataclass(frozen=True)
class TernaryPreparation:
    valid: pd.DataFrame
    invalid: pd.DataFrame
    source_columns: tuple[str, str, str]
    normalization_requested: str
    normalization_applied: str

    @property
    def total_rows(self) -> int:
        return len(self.valid) + len(self.invalid)

    @property
    def valid_rows(self) -> int:
        return len(self.valid)

    @property
    def invalid_rows(self) -> int:
        return len(self.invalid)


def _validate_columns(dataframe: pd.DataFrame, columns: tuple[str, str, str]) -> None:
    if len(set(columns)) != 3:
        raise ValueError("Для треугольной диаграммы нужно выбрать три разные колонки")
    missing = [column for column in columns if column not in dataframe.columns]
    if missing:
        raise ValueError("Не найдены колонки: " + ", ".join(missing))


def _row_reason(raw: pd.DataFrame, numeric: pd.DataFrame) -> pd.Series:
    reasons = pd.Series("", index=raw.index, dtype="object")
    missing_mask = raw.isna().any(axis=1)
    non_numeric_mask = (~raw.isna()).any(axis=1) & numeric.isna().any(axis=1) & ~missing_mask
    non_finite_mask = pd.Series(
        ~np.isfinite(numeric.to_numpy(dtype=float)).all(axis=1),
        index=numeric.index,
    )
    negative_mask = numeric.lt(0).any(axis=1)
    sum_values = numeric.sum(axis=1, min_count=3)
    zero_sum_mask = sum_values.le(0) & sum_values.notna()

    reasons.loc[missing_mask] = "missing_component"
    reasons.loc[non_numeric_mask & reasons.eq("")] = "non_numeric"
    reasons.loc[non_finite_mask & reasons.eq("")] = "non_finite"
    reasons.loc[negative_mask & reasons.eq("")] = "negative_component"
    reasons.loc[zero_sum_mask & reasons.eq("")] = "sum_not_positive"
    return reasons


def _normalization_mode(sums: pd.Series, requested: str) -> str:
    requested = str(requested or "auto").lower()
    if requested not in {"auto", "normalize", "already"}:
        raise ValueError("Неизвестный режим нормировки ternary")
    if requested != "auto":
        return requested

    finite = pd.to_numeric(sums, errors="coerce").replace([np.inf, -np.inf], np.nan).dropna()
    if finite.empty:
        return "normalize"
    median = float(finite.median())
    if np.isclose(median, 1.0, rtol=0.0, atol=0.05):
        return "fraction_to_100"
    if np.isclose(median, 100.0, rtol=0.0, atol=2.0):
        return "already"
    return "normalize"


def _normalize_components(
    numeric: pd.DataFrame,
    sums: pd.Series,
    applied_mode: str,
) -> pd.DataFrame:
    result = numeric.astype(float).copy()
    if applied_mode == "fraction_to_100":
        return result * 100.0
    if applied_mode == "already":
        return result
    return result.div(sums, axis=0) * 100.0


def ternary_to_cartesian(
    a: pd.Series | np.ndarray,
    b: pd.Series | np.ndarray,
    c: pd.Series | np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Convert A-left, B-right, C-top ternary coordinates to an equilateral triangle."""
    aa = np.asarray(a, dtype=float)
    bb = np.asarray(b, dtype=float)
    cc = np.asarray(c, dtype=float)
    total = aa + bb + cc
    with np.errstate(divide="ignore", invalid="ignore"):
        x = (bb + 0.5 * cc) / total
        y = (sqrt(3.0) / 2.0) * cc / total
    return x, y


def prepare_ternary(
    dataframe: pd.DataFrame,
    a_col: str,
    b_col: str,
    c_col: str,
    normalization: str = "auto",
) -> TernaryPreparation:
    """Validate, normalize and enrich one ternary view without mutating source data."""
    columns = (str(a_col), str(b_col), str(c_col))
    _validate_columns(dataframe, columns)

    source = dataframe.copy()
    raw = source.loc[:, list(columns)]
    numeric = raw.apply(pd.to_numeric, errors="coerce")
    reasons = _row_reason(raw, numeric)
    numeric_sums = numeric.sum(axis=1, min_count=3)

    valid_mask = reasons.eq("")
    valid = source.loc[valid_mask].copy()
    invalid = source.loc[~valid_mask].copy()
    invalid[TERNARY_REASON] = reasons.loc[~valid_mask]

    if valid.empty:
        return TernaryPreparation(
            valid=valid,
            invalid=invalid,
            source_columns=columns,
            normalization_requested=str(normalization),
            normalization_applied="normalize",
        )

    valid_numeric = numeric.loc[valid_mask].copy()
    valid_sums = numeric_sums.loc[valid_mask].astype(float)
    applied = _normalization_mode(valid_sums, normalization)
    normalized = _normalize_components(valid_numeric, valid_sums, applied)
    finite_normalized = np.isfinite(normalized.to_numpy(dtype=float)).all(axis=1)
    if not finite_normalized.all():
        failed_index = normalized.index[~finite_normalized]
        invalid_extra = source.loc[failed_index].copy()
        invalid_extra[TERNARY_REASON] = "non_finite"
        invalid = pd.concat([invalid, invalid_extra], axis=0)
        keep_index = normalized.index[finite_normalized]
        valid = valid.loc[keep_index].copy()
        valid_numeric = valid_numeric.loc[keep_index]
        valid_sums = valid_sums.loc[keep_index]
        normalized = normalized.loc[keep_index]

    if valid.empty:
        return TernaryPreparation(
            valid=valid,
            invalid=invalid,
            source_columns=columns,
            normalization_requested=str(normalization),
            normalization_applied=applied,
        )

    valid[TERNARY_A] = normalized.iloc[:, 0].to_numpy(dtype=float)
    valid[TERNARY_B] = normalized.iloc[:, 1].to_numpy(dtype=float)
    valid[TERNARY_C] = normalized.iloc[:, 2].to_numpy(dtype=float)
    valid[TERNARY_SUM] = valid_sums.to_numpy(dtype=float)
    x, y = ternary_to_cartesian(valid[TERNARY_A], valid[TERNARY_B], valid[TERNARY_C])
    valid[TERNARY_X] = x
    valid[TERNARY_Y] = y

    return TernaryPreparation(
        valid=valid,
        invalid=invalid,
        source_columns=columns,
        normalization_requested=str(normalization),
        normalization_applied=applied,
    )


def invalid_reason_counts(preparation: TernaryPreparation) -> pd.DataFrame:
    if preparation.invalid.empty or TERNARY_REASON not in preparation.invalid.columns:
        return pd.DataFrame(columns=["Причина", "Количество"])
    labels = {
        "missing_component": "нет одного из компонентов",
        "non_numeric": "нечисловое значение",
        "non_finite": "бесконечное/невалидное числовое значение",
        "negative_component": "отрицательный компонент",
        "sum_not_positive": "сумма компонентов ≤ 0",
    }
    counts = preparation.invalid[TERNARY_REASON].value_counts(dropna=False)
    return pd.DataFrame(
        {
            "Причина": [labels.get(str(reason), str(reason)) for reason in counts.index],
            "Количество": counts.astype(int).tolist(),
        }
    )
