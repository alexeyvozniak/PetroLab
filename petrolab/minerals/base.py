from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# Молярные массы, г/моль. Используются только для прозрачных простых индексов.
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
        """Базовые воспроизводимые индексы без предположений о Fe3+/Fe2+ и H2O."""
        out = df.copy()
        if "MgO" in out.columns and "FeO" in out.columns:
            mg = pd.to_numeric(out["MgO"], errors="coerce") / MOLAR_MASS["MgO"]
            fe = pd.to_numeric(out["FeO"], errors="coerce") / MOLAR_MASS["FeO"]
            denom = mg + fe
            out["Mg#"] = np.where(denom > 0, mg / denom, np.nan)
        return out
