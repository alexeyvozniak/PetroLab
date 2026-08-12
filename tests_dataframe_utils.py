from __future__ import annotations

import pandas as pd

from petrolab.dataframe_utils import (
    apply_column_filters,
    apply_quick_filter,
    compute_changes,
    display_value,
    row_identity,
)


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

print("dataframe utility tests: OK")
