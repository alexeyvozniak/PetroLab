from __future__ import annotations

import pandas as pd

from petrolab.dataframe_utils import (
    apply_column_filters,
    apply_quick_filter,
    compute_changes,
    display_value,
    row_identity,
)
from petrolab.io_utils import add_qc_columns, normalize_columns_with_map
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

# Detection-limit qualifiers are analytical information, not missing data. Header/unit
# normalization must scale the threshold and preserve the qualifier itself.
censored = pd.DataFrame({
    "La ppb": ["<10", 250.0],
    "Ce ppm": ["≤0.02", 1.5],
    "SiO2": [50.0, 51.0],
    "FeO": [8.0, 9.0],
})
normalized, mapping = normalize_columns_with_map(censored)
assert normalized.columns.tolist() == ["La [µg/g]", "Ce [µg/g]", "SiO2", "FeO"]
assert normalized.loc[0, "La [µg/g]"] == "<0.01"
assert float(normalized.loc[1, "La [µg/g]"]) == 0.25
assert normalized.loc[0, "Ce [µg/g]"] == "≤0.02"
assert mapping["La [µg/g]"]["source_unit"].lower() == "ppb"

# QC calculations may use a numeric view of chemistry, but must not overwrite the
# preserved qualifier in the dataframe returned to the rest of PetroLab.
qc = add_qc_columns(normalized)
assert qc.loc[0, "La [µg/g]"] == "<0.01"
assert qc.loc[0, "Ce [µg/g]"] == "≤0.02"
assert "Σ оксидов" in qc.columns

print("dataframe utility tests: OK")
