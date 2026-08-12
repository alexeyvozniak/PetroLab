from __future__ import annotations

import pandas as pd

from petrolab.column_schema import (
    apply_semantic_mapping,
    canonicalize_header,
    inspect_sheet_schema,
)
from petrolab.io_utils import normalize_columns_with_map

assert canonicalize_header("SiO₂") == "SiO2"
assert canonicalize_header(" SiO2 (wt. %) ") == "SiO2"
assert canonicalize_header("Al₂O₃") == "Al2O3"
assert canonicalize_header("FeOt") == "FeO"
assert canonicalize_header("Na₂O wt%") == "Na2O"
assert canonicalize_header("Generation custom") == "Generation custom"

raw = pd.DataFrame(
    {
        "Sample ID": ["A"],
        "Gen": ["core"],
        "SiO₂": [40.0],
        "MgO": [20.0],
        "FeOt": [8.0],
    }
)
normalized, source_map = normalize_columns_with_map(raw)
assert list(normalized.columns) == ["Sample ID", "Gen", "SiO2", "MgO", "FeO"]
assert source_map["SiO2"]["original"] == "SiO₂"
assert source_map["FeO"]["original"] == "FeOt"

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

ambiguous = inspect_sheet_schema(["Sample", "Group", "SiO2"])
assert "Generation" not in ambiguous.suggested
assert ambiguous.weak_candidates["Generation"] == ("Group",)

collision_raw = pd.DataFrame({"FeO": [1.0], "FeOt": [2.0]})
collision, collision_map = normalize_columns_with_map(collision_raw)
assert list(collision.columns) == ["FeO", "FeO__2"]
assert collision_map["FeO"]["column_index"] == 1
assert collision_map["FeO__2"]["column_index"] == 2

print("column schema tests: OK")
