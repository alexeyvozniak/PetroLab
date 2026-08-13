from __future__ import annotations

import numpy as np
import pandas as pd

from petrolab.statistics import (
    correlation_matrix,
    descriptive_statistics,
    numeric_feature_candidates,
    prepare_matrix,
)


dataframe = pd.DataFrame(
    {
        "A": [1.0, float("inf"), 3.0, 4.0],
        "B": [10.0, 11.0, 12.0, 13.0],
        "OnlyInf": [float("inf"), float("-inf"), np.nan, np.nan],
    }
)

candidates = numeric_feature_candidates(dataframe)
assert "A" in candidates
assert "B" in candidates
assert "OnlyInf" not in candidates

prepared = prepare_matrix(dataframe, ["A", "B"], impute="median")
assert np.isfinite(prepared.matrix).all()

correlation = correlation_matrix(dataframe, ["A", "B"])
assert np.isfinite(correlation.loc["A", "B"])

stats = descriptive_statistics(dataframe, ["A", "B"])
assert int(stats.loc["A", "missing"]) == 1

try:
    prepare_matrix(dataframe, ["OnlyInf"])
except ValueError as exc:
    assert "конечных значений" in str(exc) or "не осталось строк" in str(exc)
else:
    raise AssertionError("An all-infinite feature must not enter sklearn pipelines")

print("statistics tests: OK")
