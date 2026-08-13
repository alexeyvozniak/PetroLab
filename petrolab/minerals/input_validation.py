from __future__ import annotations

import numpy as np
import pandas as pd

from .formulae import HALOGENS, OXIDES


SCIENTIFIC_FORMULA_COLUMNS = set(OXIDES) | set(HALOGENS) | {"FeOt", "Fe2O3t"}


def _row_label(dataframe: pd.DataFrame, index: object) -> str:
    if "_source_row" in dataframe.columns:
        try:
            value = dataframe.at[index, "_source_row"]
            if pd.notna(value):
                return f"строка Excel {int(value)}"
        except (KeyError, TypeError, ValueError):
            pass
    return f"строка {index}"


def validate_formula_inputs(dataframe: pd.DataFrame) -> None:
    """Reject supplied chemistry that has no physical structural-formula interpretation.

    Empty cells remain missing analytical values and are handled by row-validity/QC logic.
    Non-empty nonnumeric tokens, infinities and negative concentrations are different: they
    must not enter oxygen normalization and yield a plausible-looking APFU result.
    """
    problems: list[str] = []
    for column in dataframe.columns:
        name = str(column)
        if name not in SCIENTIFIC_FORMULA_COLUMNS:
            continue

        raw = dataframe[column]
        numeric = pd.to_numeric(raw, errors="coerce")
        text = raw.astype("string").str.strip()
        nonempty = raw.notna() & text.ne("")
        nonnumeric = nonempty & numeric.isna()
        finite = pd.Series(np.isfinite(numeric.to_numpy(dtype=float)), index=dataframe.index)
        nonfinite = numeric.notna() & ~finite
        negative = numeric.lt(0).fillna(False)

        for mask, reason in (
            (nonnumeric, "нечисловое значение"),
            (nonfinite, "нефинитное значение"),
            (negative, "отрицательная концентрация"),
        ):
            for index in dataframe.index[mask]:
                problems.append(f"{name}, {_row_label(dataframe, index)}: {reason}")
                if len(problems) >= 12:
                    break
            if len(problems) >= 12:
                break
        if len(problems) >= 12:
            break

    if problems:
        raise ValueError(
            "Структурная формула не рассчитана: обнаружены невалидные химические входы. "
            + "; ".join(problems)
        )
