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
        iron_column = None
        if "FeO" in out.columns:
            iron_column = "FeO"
        elif "FeOt" in out.columns:
            iron_column = "FeOt"

        if "MgO" in out.columns and iron_column:
            mg = pd.to_numeric(out["MgO"], errors="coerce") / MOLAR_MASS["MgO"]
            fe = pd.to_numeric(out[iron_column], errors="coerce") / MOLAR_MASS["FeO"]
            denom = mg + fe
            out["Mg#"] = np.where(denom > 0, mg / denom, np.nan)
            if iron_column == "FeOt":
                out["Mg#_Fe_basis"] = "FeOt (total Fe as FeO)"
        return out
