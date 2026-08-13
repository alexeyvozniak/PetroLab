import os

import numpy as np
import pandas as pd

# This suite verifies production semantics even when invoked by the legacy BAT smoke
# subprocess, whose PETROLAB_CI flag exists only to keep historical fixtures readable.
os.environ.pop("PETROLAB_CI", None)

from petrolab.column_schema import canonicalize_header
from petrolab.extended_plotting import prepare_pattern
from petrolab.io_utils import normalize_columns_with_map
from petrolab.measurement_semantics import apply_measurement_overrides
from petrolab.services.formula_service import calculate_formula_safe
from petrolab.ternary_presets import TERNARY_PRESETS, apply_preset_projection


# Detection-limit qualifiers survive unit normalization instead of becoming NaN.
censored_raw = pd.DataFrame({"La ppb": ["<100", 250.0]})
censored, _ = normalize_columns_with_map(censored_raw)
assert censored["La [µg/g]"].tolist() == ["<0.1", 0.25]

# Compact Cyrillic concentration units remain recognized after Unicode normalization.
assert canonicalize_header("Ba нг г⁻¹") == "Ba [µg/g]"
assert canonicalize_header("U пг г⁻¹") == "U [µg/g]"

# Bare FeO/Fe2O3 headers are ambiguous at import time and must be confirmed explicitly.
feo_frame, feo_map = normalize_columns_with_map(pd.DataFrame({"FeO": [8.0], "MgO": [20.0]}))
try:
    apply_measurement_overrides(feo_frame, feo_map, {})
except ValueError as exc:
    assert "FeO" in str(exc)
else:
    raise AssertionError("Bare FeO must require explicit reporting semantics")

feo_total, _, feo_semantics = apply_measurement_overrides(
    feo_frame, feo_map, {"FeO": "FeOt"}
)
assert "FeOt" in feo_total.columns and "FeO" not in feo_total.columns
assert feo_semantics == {"FeO": "FeOt"}

fe3_frame, fe3_map = normalize_columns_with_map(pd.DataFrame({"Fe2O3": [10.0]}))
try:
    apply_measurement_overrides(fe3_frame, fe3_map, {})
except ValueError as exc:
    assert "Fe2O3" in str(exc)
else:
    raise AssertionError("Bare Fe2O3 must require explicit reporting semantics")

# Canonical duplicates must stop import instead of preserving an order-dependent __2 value.
duplicate, duplicate_map = normalize_columns_with_map(
    pd.DataFrame({"Rb ppm": [1.0], "Rb (µg/g)": [2.0]})
)
try:
    apply_measurement_overrides(duplicate, duplicate_map, {})
except ValueError as exc:
    assert "конфликт" in str(exc).lower()
else:
    raise AssertionError("Duplicate scientific inputs must be blocked")

# Structural formulae reject physically invalid numeric inputs.
try:
    calculate_formula_safe(
        pd.DataFrame([{"SiO2": 40.0, "MgO": -1.0, "FeO": 10.0}]),
        "olivine", "ol_4o_fe2",
    )
except ValueError as exc:
    assert "отриц" in str(exc).lower()
else:
    raise AssertionError("Negative chemistry must not enter structural formulae")

# Censored values are preserved in source data but require a deliberate numerical choice before APFU.
try:
    calculate_formula_safe(
        pd.DataFrame([{"SiO2": 40.0, "MgO": 20.0, "FeO": "<0.01"}]),
        "olivine", "ol_4o_fe2",
    )
except ValueError as exc:
    assert "detection-limit" in str(exc) or "censored" in str(exc)
else:
    raise AssertionError("Censored chemistry must not be silently substituted in APFU")

# Henderson 32-O framework balance does not silently reinterpret ferrous iron as ferric iron.
try:
    calculate_formula_safe(
        pd.DataFrame([{"SiO2": 43.0, "Al2O3": 34.0, "Na2O": 16.0, "K2O": 5.0, "FeO": 1.0}]),
        "nepheline", "ne_henderson32",
    )
except ValueError as exc:
    assert "Henderson" in str(exc) and "Fe" in str(exc)
else:
    raise AssertionError("Henderson nepheline must reject Fe2+ input in the current model")

# MinPlot titanite uses a ferric calculation basis while retaining the source FeO column.
titanite = calculate_formula_safe(
    pd.DataFrame([{"SiO2": 30.5, "TiO2": 35.0, "CaO": 28.0, "Al2O3": 2.0, "FeO": 2.0, "F": 0.5}]),
    "titanite", "ttn_minplot",
).data.iloc[0]
assert "FeO" in titanite.index
assert float(titanite.get("apfu_Fe3", 0.0)) > 0

# Mineral-scoped presets cannot consume an otherwise numerically compatible foreign mineral.
mixed = pd.DataFrame([
    {"Минерал": "clinopyroxene", "apfu_Ca": 0.8, "apfu_Mg": 0.9, "apfu_Fe2": 0.25, "Q": 1.85, "J": 0.10},
    {"Минерал": "garnet", "apfu_Ca": 0.8, "apfu_Mg": 0.9, "apfu_Fe2": 0.25, "Q": 1.85, "J": 0.10},
])
projected, components = apply_preset_projection(mixed, TERNARY_PRESETS["pyroxene_wo_en_fs"])
assert len(projected) == 1
assert projected["Минерал"].iloc[0] == "clinopyroxene"
assert projected[list(components)].notna().all(axis=1).all()

# Scientific patterns do not connect through ±inf or non-positive values on log plots.
pattern = prepare_pattern(
    pd.DataFrame({"La [µg/g]": [1.0, np.inf, 2.0], "Ce [µg/g]": [2.0, 3.0, -1.0]}),
    ["La", "Ce"],
)
assert len(pattern.data) == 1
assert np.isfinite(pattern.data.to_numpy(dtype=float)).all()
assert (pattern.data.to_numpy(dtype=float) > 0).all()

print("v0.11 integrity tests: OK")
