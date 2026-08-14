from __future__ import annotations

import numpy as np
import pandas as pd

from petrolab.minerals.input_validation import validate_formula_inputs


# A genuinely blank analytical cell is missing information, not a nonphysical number.
validate_formula_inputs(
    pd.DataFrame({"SiO2": [40.0, None], "MgO": [20.0, 19.0], "FeO": [8.0, 9.0]})
)

for dataframe, expected in (
    (pd.DataFrame({"SiO2": [40.0], "MgO": [-0.2]}), "отрицательная"),
    (pd.DataFrame({"SiO2": [np.inf], "MgO": [20.0]}), "нефинитное"),
    (pd.DataFrame({"SiO2": ["bad"], "MgO": [20.0]}), "нечисловое"),
):
    try:
        validate_formula_inputs(dataframe)
    except ValueError as exc:
        assert expected in str(exc)
    else:
        raise AssertionError(f"Invalid chemistry must be rejected: {dataframe.to_dict()}")

print("formula input validation tests: OK")
