from __future__ import annotations

import numpy as np
import pandas as pd

from petrolab.minerals import calculate_formula
from petrolab.minerals.input_validation import validate_formula_inputs


# A genuinely blank analytical cell is missing information, not a nonphysical number.
validate_formula_inputs(
    pd.DataFrame({"SiO2": [40.0, None], "MgO": [20.0, 19.0], "FeO": [8.0, 9.0]})
)

# Below-zero analytical concentrations are allowed through validation: the runtime
# floors them to zero only in its calculation copy.
validate_formula_inputs(pd.DataFrame({"SiO2": [40.0], "MgO": [-0.2], "P2O5": [-0.01]}))

for dataframe, expected in (
    (pd.DataFrame({"SiO2": [np.inf], "MgO": [20.0]}), "нефинитное"),
    (pd.DataFrame({"SiO2": ["bad"], "MgO": [20.0]}), "нечисловое"),
):
    try:
        validate_formula_inputs(dataframe)
    except ValueError as exc:
        assert expected in str(exc)
    else:
        raise AssertionError(f"Invalid chemistry must be rejected: {dataframe.to_dict()}")

cpx = pd.DataFrame(
    {
        "SiO2": [51.0],
        "TiO2": [0.7],
        "Al2O3": [3.8],
        "Cr2O3": [-0.01],
        "FeO": [6.4],
        "MnO": [0.1],
        "MgO": [15.8],
        "CaO": [20.9],
        "Na2O": [0.5],
        "K2O": [0.03],
        "P2O5": [-0.02],
    }
)
raw = cpx.copy(deep=True)
result = calculate_formula(cpx, "clinopyroxene", "px_6o_fe2")
assert float(result.data.loc[0, "Cr2O3"]) == -0.01
assert float(result.data.loc[0, "P2O5"]) == -0.02
assert abs(float(result.data.loc[0, "apfu_Cr"])) < 1e-15
assert abs(float(result.data.loc[0, "apfu_P"])) < 1e-15
assert "Cr2O3: 1" in result.note_ru
assert "P2O5: 1" in result.note_ru
pd.testing.assert_frame_equal(cpx, raw)

print("formula input validation tests: OK")
