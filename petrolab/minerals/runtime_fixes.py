from __future__ import annotations

import pandas as pd

from . import formulae as _formulae


_ORIGINAL_MICA = _formulae.calc_mica


def calc_mica_safe(df: pd.DataFrame, method_id: str) -> _formulae.CalculationResult:
    """Run mica recalculation safely when F and/or Cl were not measured.

    Missing halogens are chemically equivalent to zero for the routine
    maximum-OH estimate. The original input schema is preserved in the output.
    """
    missing = [name for name in ("F", "Cl") if name not in df.columns]
    if not missing:
        return _ORIGINAL_MICA(df, method_id)

    work = df.copy()
    for name in missing:
        work[name] = pd.Series(0.0, index=work.index, dtype=float)

    result = _ORIGINAL_MICA(work, method_id)
    cleaned = result.data.drop(columns=missing, errors="ignore")
    return _formulae.CalculationResult(cleaned, result.note_ru)


def install_runtime_fixes() -> None:
    _formulae.CALCULATORS["mica"] = calc_mica_safe
