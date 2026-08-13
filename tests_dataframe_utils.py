from __future__ import annotations

import copy

import pandas as pd

from petrolab.dataframe_utils import (
    apply_column_filters,
    apply_quick_filter,
    compute_changes,
    display_value,
    row_identity,
)
from petrolab.measurement_semantics import apply_measurement_overrides
from petrolab.outliers import apply_numeric_ranges, exclude_analysis_ids, robust_outliers


original = pd.DataFrame(
    {
        "_analysis_id": ["a1", "a2"],
        "_dataset_id": [10, 10],
        "_source_row": [2, 3],
        "Sample": ["K1", "K2"],
        "SiO2": [40.0, 41.0],
        "Σ оксидов": [99.0, 100.0],
    }
)
edited = original.copy()
edited.loc[0, "SiO2"] = 40.5
edited.loc[0, "Σ оксидов"] = 1.0
changes = compute_changes(original, edited, protected_columns={"Σ оксидов"})
assert len(changes) == 1
assert changes[0]["analysis_id"] == "a1"
assert changes[0]["source_row"] == 2
assert changes[0]["column_name"] == "SiO2"
assert changes[0]["new_value"] == 40.5

quick = apply_quick_filter(original, "k2")
assert list(quick["Sample"]) == ["K2"]

filtered = apply_column_filters(original, {"Sample": ["K1"]})
assert list(filtered["Sample"]) == ["K1"]

assert row_identity(original.iloc[0]).startswith("Sample: K1")
assert display_value(pd.NA) == ""
assert display_value(12) == "12"

# Manual ranges are reversible views; the source dataframe remains untouched.
chem = pd.DataFrame(
    {
        "_analysis_id": [f"p{i}" for i in range(8)],
        "Rb [µg/g]": [100, 105, 98, 102, 101, 99, 103, 900],
        "apfu_AlIV": [1.10, 1.12, 1.09, 1.11, 1.10, 1.08, 1.13, 2.50],
    }
)
ranged = apply_numeric_ranges(chem, {"Rb [µg/g]": (95.0, 200.0)})
assert len(ranged) == 7
assert len(chem) == 8
assert "p7" not in set(ranged["_analysis_id"])

mad = robust_outliers(chem, ["Rb [µg/g]", "apfu_AlIV"], method="MAD", threshold=3.5)
assert mad.outlier_count == 1
assert chem.loc[mad.outlier_mask, "_analysis_id"].tolist() == ["p7"]
assert len(chem.loc[mad.keep_mask]) == 7

iqr = robust_outliers(chem, ["Rb [µg/g]"], method="IQR", threshold=1.5)
assert iqr.outlier_count == 1
assert chem.loc[iqr.outlier_mask, "_analysis_id"].tolist() == ["p7"]

manual = exclude_analysis_ids(chem, ["p1", "p7"])
assert set(manual["_analysis_id"]) == {"p0", "p2", "p3", "p4", "p5", "p6"}
assert len(chem) == 8

# Schema updates must be copy-on-write. Reinterpreting Fe2O3 in one import must not
# mutate the original provenance dictionary that may still be cached by another sheet.
measurement_frame = pd.DataFrame({"Fe2O3": [9.5], "SiO2": [40.0]})
measurement_map = {
    "Fe2O3": {"original": "Fe2O3"},
    "SiO2": {"original": "SiO2"},
    "__schema__": {"semantic": {"Generation": "Gen"}},
}
measurement_snapshot = copy.deepcopy(measurement_map)
renamed, mapped, stored = apply_measurement_overrides(
    measurement_frame,
    measurement_map,
    {"Fe2O3": "Fe2O3t"},
)
assert measurement_map == measurement_snapshot
assert "Fe2O3t" in renamed.columns and "Fe2O3" not in renamed.columns
assert mapped["__schema__"]["semantic"] == {"Generation": "Gen"}
assert mapped["__schema__"]["measurement"] == stored
assert stored == {"Fe2O3": "Fe2O3t"}

print("dataframe utility tests: OK")
