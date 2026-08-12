from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

MOLAR_MASS = {
    "FeO": 71.844,
    "MgO": 40.3044,
    "CaO": 56.0774,
    "Na2O": 61.9789,
    "K2O": 94.196,
}


def _has_duplicate_input(columns: pd.Index, base: str) -> bool:
    prefix = f"{base}__"
    return any(str(column).startswith(prefix) for column in columns)


def _numeric_or_nan(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(np.nan, index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


@dataclass(frozen=True)
class MineralModule:
    key: str
    name_ru: str
    group_ru: str
    description: str
    typical_oxides: tuple[str, ...] = field(default_factory=tuple)

    def calculate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Базовые индексы; FeOt допускается только как явно помеченный total Fe as FeO."""
        out = df.copy()
        duplicate_inputs = [
            base for base in ("MgO", "FeO", "FeOt")
            if _has_duplicate_input(out.columns, base)
        ]
        if duplicate_inputs:
            out["QC Mg#"] = (
                "Mg# не рассчитан: конфликтующие колонки " + ", ".join(duplicate_inputs)
            )
            return out

        if "MgO" not in out.columns or not ({"FeO", "FeOt"} & set(out.columns)):
            return out

        mg_raw = _numeric_or_nan(out, "MgO")
        feo = _numeric_or_nan(out, "FeO")
        feot = _numeric_or_nan(out, "FeOt")
        overlap = feo.notna() & feot.notna()
        if overlap.any():
            out["QC Mg#"] = (
                "Mg# не рассчитан: в одной или нескольких строках одновременно заданы FeO и FeOt"
            )
            return out

        # Mixed historical tables may use FeO in some rows and FeOt in others. Preserve
        # the distinction row by row instead of discarding FeOt merely because FeO exists.
        fe_raw = feo.combine_first(feot)
        mg = mg_raw / MOLAR_MASS["MgO"]
        fe = fe_raw / MOLAR_MASS["FeO"]
        denom = mg + fe
        out["Mg#"] = np.where(denom > 0, mg / denom, np.nan)

        basis = pd.Series("", index=out.index, dtype="string")
        basis.loc[feo.notna()] = "FeO"
        basis.loc[feo.isna() & feot.notna()] = "FeOt (total Fe as FeO)"
        out["Mg#_Fe_basis"] = basis
        return out
