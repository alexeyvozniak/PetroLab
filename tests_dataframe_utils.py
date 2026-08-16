from __future__ import annotations

import json

import pandas as pd

from petrolab.dataframe_utils import (
    apply_column_filters,
    apply_quick_filter,
    compute_changes,
    dataset_label,
    display_value,
    row_identity,
    values_equal,
)
from petrolab.io_utils import add_qc_columns, normalize_columns_with_map
from petrolab.outliers import apply_numeric_ranges, exclude_analysis_ids, robust_outliers
from petrolab.ui.editability import common_editable_source_columns


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

literal = pd.DataFrame(
    {
        "Sample": ["A[1]", "A1", "B.2"],
        "Generation": ["core", "rim", "core"],
    }
)
assert apply_quick_filter(literal, "[")["Sample"].tolist() == ["A[1]"]

filtered = apply_column_filters(original, {"Sample": ["K1"]})
assert list(filtered["Sample"]) == ["K1"]

assert row_identity(original.iloc[0]).startswith("Sample: K1")
assert display_value(pd.NA) == ""
assert display_value(12) == "12"
assert values_equal(float("inf"), float("inf"))
assert values_equal(float("-inf"), float("-inf"))
assert not values_equal(float("inf"), float("-inf"))

label = dataset_label(
    {
        "id": 42,
        "project_name": "Kola",
        "name": "Mica",
        "row_count": 602,
        "source_filename": "mica.xlsx",
    }
)
assert label == "Kola · Mica · 602 строк · mica.xlsx"
assert "ID 42" not in label

# The unified editor is column-oriented. For mixed schemas, only the physical source
# intersection is writable; otherwise an empty union cell could become a DB-only pseudo-source.
dataset_a = {
    "id": 1,
    "column_map_json": json.dumps(
        {
            "Sample": {"original": "Sample"},
            "SiO2": {"original": "SiO2"},
            "La [µg/g]": {"original": "La ppm"},
            "__schema__": {"semantic": {"Sample": "Sample"}},
        }
    ),
}
dataset_b = {
    "id": 2,
    "column_map_json": json.dumps(
        {
            "Sample": {"original": "Sample"},
            "SiO2": {"original": "SiO2"},
        }
    ),
}
assert common_editable_source_columns([dataset_a, dataset_b], [1]) == {
    "Sample",
    "SiO2",
    "La [µg/g]",
}
assert common_editable_source_columns([dataset_a, dataset_b], [1, 2]) == {
    "Sample",
    "SiO2",
}

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
