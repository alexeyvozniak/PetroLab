from __future__ import annotations

import pandas as pd

from petrolab.column_schema import (
    apply_semantic_mapping,
    canonicalize_header,
    describe_header,
    inspect_sheet_schema,
    resolve_semantic_mapping,
)
from petrolab.io_utils import normalize_columns_with_map

assert canonicalize_header("SiO₂") == "SiO2"
assert canonicalize_header(" SiO2 (wt. %) ") == "SiO2"
assert canonicalize_header("Al₂O₃") == "Al2O3"
assert canonicalize_header("FeOt") == "FeOt"
assert canonicalize_header("FeO total") == "FeOt"
assert canonicalize_header("Na₂O wt%") == "Na2O"
assert canonicalize_header("Generation custom") == "Generation custom"

assert canonicalize_header("Rb ppm") == "Rb [µg/g]"
assert canonicalize_header("Rb (µg/g)") == "Rb [µg/g]"
assert canonicalize_header("Yb, мкг/г") == "Yb [µg/g]"
assert canonicalize_header("Ba ppb") == "Ba [µg/g]"
assert canonicalize_header("Rb") == "Rb"
assert describe_header("Ba ppb").to_canonical_factor == 1e-3
assert describe_header("Ba ppb").to_source_factor == 1e3

raw = pd.DataFrame(
    {
        "Sample ID": ["A"],
        "Gen": ["core"],
        "SiO₂": [40.0],
        "MgO": [20.0],
        "FeOt": [8.0],
        "Rb ppm": [150.0],
        "Ba ppb": [1200.0],
    }
)
normalized, source_map = normalize_columns_with_map(raw)
assert list(normalized.columns) == [
    "Sample ID", "Gen", "SiO2", "MgO", "FeOt", "Rb [µg/g]", "Ba [µg/g]"
]
assert source_map["SiO2"]["original"] == "SiO₂"
assert source_map["FeOt"]["original"] == "FeOt"
assert source_map["FeOt"]["warning"] == "total Fe as FeO"
assert float(normalized.loc[0, "Rb [µg/g]"]) == 150.0
assert float(normalized.loc[0, "Ba [µg/g]"]) == 1.2
assert source_map["Ba [µg/g]"]["to_source_factor"] == 1000.0

schema = inspect_sheet_schema(normalized.columns)
assert schema.suggested["Sample"] == "Sample ID"
assert schema.suggested["Generation"] == "Gen"

mapped, mapped_source, semantic = apply_semantic_mapping(
    normalized,
    source_map,
    {"Sample": "Sample ID", "Generation": "Gen"},
)
assert "Sample" in mapped.columns
assert "Generation" in mapped.columns
assert mapped_source["Generation"]["original"] == "Gen"
assert semantic == {"Sample": "Sample ID", "Generation": "Gen"}

# A safe header rename can be recovered without asking the user again.
resolved = resolve_semantic_mapping(
    ["Sample", "Generation", "SiO2"],
    {"Sample": "Sample ID", "Generation": "Gen"},
)
assert resolved == {"Sample": "Sample", "Generation": "Generation"}

ambiguous = inspect_sheet_schema(["Sample", "Group", "SiO2"])
assert "Generation" not in ambiguous.suggested
assert ambiguous.weak_candidates["Generation"] == ("Group",)

# Same canonical quantity is not silently merged; the second column gets a technical suffix.
collision_raw = pd.DataFrame({"Rb ppm": [1.0], "Rb (µg/g)": [2.0]})
collision, collision_map = normalize_columns_with_map(collision_raw)
assert list(collision.columns) == ["Rb [µg/g]", "Rb [µg/g]__2"]
assert collision_map["Rb [µg/g]"]["column_index"] == 1
assert collision_map["Rb [µg/g]__2"]["column_index"] == 2

# FeO and FeOt remain semantically distinct.
iron_raw = pd.DataFrame({"FeO": [1.0], "FeOt": [2.0]})
iron, _ = normalize_columns_with_map(iron_raw)
assert list(iron.columns) == ["FeO", "FeOt"]

print("column schema tests: OK")
