from __future__ import annotations

import numpy as np
import pandas as pd

from petrolab.minerals.input_validation import validate_formula_inputs
from petrolab.services.formula_service import _align


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

# A calculator may reorder rows internally. Formula values must return to the
# physical analysis identified by immutable _analysis_id, never by DataFrame order.
source = pd.DataFrame({"_analysis_id": ["first", "second"], "SiO2": [40.0, 41.0]})
calculated = pd.DataFrame({"_analysis_id": ["second", "first"], "formula_value": [2.0, 1.0]})
aligned = _align(source, calculated)
assert aligned["_analysis_id"].tolist() == ["first", "second"]
assert aligned["formula_value"].tolist() == [1.0, 2.0]

try:
    _align(source, pd.DataFrame({"_analysis_id": ["first", "other"], "formula_value": [1.0, 3.0]}))
except ValueError as exc:
    assert "не совпадает" in str(exc)
else:
    raise AssertionError("a formula result with a different analysis set must be rejected")

print("formula input validation tests: OK")
