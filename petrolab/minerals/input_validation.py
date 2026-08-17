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
    """Reject inputs that cannot be interpreted numerically by structural formulas.

    Small negative analytical concentrations are a legitimate output of background
    correction near the detection limit. They are therefore not rejected here;
    the formula runtime floors them to zero only in its calculation copy and keeps
    the raw source values unchanged. Nonnumeric and infinite values remain hard
    errors because they have no numerical interpretation at all.
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

        for mask, reason in (
            (nonnumeric, "нечисловое значение"),
            (nonfinite, "нефинитное значение"),
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
