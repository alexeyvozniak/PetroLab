from __future__ import annotations

import numpy as np
import pandas as pd

from petrolab.statistics import (
    correlation_matrix,
    descriptive_statistics,
    negative_concentration_counts,
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

# Analytical concentrations may be slightly negative after background correction.
# Statistics uses a zero-floored working copy but never mutates the source table.
chemistry = pd.DataFrame(
    {
        "P2O5": [-0.02, 0.10, 0.20],
        "Cr2O3": [-0.01, 0.15, 0.25],
        "εNd(t)": [-9.4, -7.5, 1.1],
    }
)
raw_copy = chemistry.copy(deep=True)
counts = negative_concentration_counts(chemistry, ["P2O5", "Cr2O3", "εNd(t)"])
assert counts == {"P2O5": 1, "Cr2O3": 1}
chem_stats = descriptive_statistics(chemistry, ["P2O5", "Cr2O3", "εNd(t)"])
assert float(chem_stats.loc["P2O5", "min"]) == 0.0
assert float(chem_stats.loc["Cr2O3", "min"]) == 0.0
assert float(chem_stats.loc["εNd(t)", "min"]) == -9.4
chem_matrix = prepare_matrix(
    chemistry,
    ["P2O5", "Cr2O3", "εNd(t)"],
    scaler="none",
    impute="median",
)
assert chem_matrix.matrix[0, 0] == 0.0
assert chem_matrix.matrix[0, 1] == 0.0
assert chem_matrix.matrix[0, 2] == -9.4
pd.testing.assert_frame_equal(chemistry, raw_copy)

# CLR cannot take log(0): a negative concentration becomes physical zero first,
# and that row is then excluded rather than receiving an invented pseudocount.
clr = prepare_matrix(
    chemistry,
    ["P2O5", "Cr2O3"],
    scaler="none",
    transform="clr",
)
assert clr.excluded_rows == 1
assert len(clr.index) == 2

print("statistics tests: OK")
