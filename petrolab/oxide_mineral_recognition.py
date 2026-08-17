from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import math


OXIDE_EXTENSION_VERSION = "2026.08.1"
OXIDE_MINERAL_KEYS = (
    "magnetite",
    "spinel",
    "chromite",
    "ilmenite",
    "fe_ti_oxide",
)


@dataclass(frozen=True)
class OxideCandidate:
    target: str
    score: float
    reasons: tuple[str, ...]


def _value(row: Mapping[str, Any], key: str) -> float:
    try:
        value = float(row.get(key, float("nan")))
    except (TypeError, ValueError):
        return float("nan")
    return value if math.isfinite(value) else float("nan")


def _optional_lt(value: float, limit: float) -> bool:
    return not math.isfinite(value) or value < limit


def score_oxide_candidates(row: Mapping[str, Any]) -> dict[str, OxideCandidate]:
    """Add species-level oxide suggestions only when routine chemistry really supports them.

    In particular, magnetite is not inferred from FeOt alone. A species-level suggestion
    requires separately interpreted FeO (Fe2+) and Fe2O3 (Fe3+) columns. The importer only
    leaves those names when the user explicitly chose separate valence semantics; total iron
    is normalized to FeOt/Fe2O3t and therefore cannot trigger this rule.
    """
    feo = _value(row, "FeO")
    fe2o3 = _value(row, "Fe2O3")
    sio2 = _value(row, "SiO2")
    tio2 = _value(row, "TiO2")
    al2o3 = _value(row, "Al2O3")
    cr2o3 = _value(row, "Cr2O3")
    mgo = _value(row, "MgO")
    mno = _value(row, "MnO")

    out: dict[str, OxideCandidate] = {}
    if not (math.isfinite(feo) and math.isfinite(fe2o3)):
        return out

    fe_total_oxides = feo + fe2o3
    other_spinels = sum(
        value for value in (al2o3, cr2o3, mgo, mno, tio2)
        if math.isfinite(value)
    )
    # Ideal magnetite is ~31.0 wt% FeO + ~69.0 wt% Fe2O3. Natural magnetite can
    # carry Ti, Mg, Mn, Al and Cr, so use a conservative broad envelope rather than
    # an artificial end-member equality.
    if (
        18.0 <= feo <= 42.0
        and 45.0 <= fe2o3 <= 78.0
        and fe_total_oxides >= 75.0
        and _optional_lt(sio2, 5.0)
        and _optional_lt(tio2, 15.0)
        and other_spinels <= 28.0
    ):
        out["magnetite (spinel-group oxide)"] = OxideCandidate(
            "magnetite (spinel-group oxide)",
            11.0,
            (
                "separate FeO and Fe2O3 measured/interpreted",
                "Fe2+-Fe3+ oxide chemistry compatible with magnetite",
            ),
        )
    return out