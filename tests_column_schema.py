from __future__ import annotations

import pandas as pd

from petrolab.column_schema import (
    apply_semantic_mapping,
    canonicalize_header,
    describe_header,
    inspect_sheet_schema,
    resolve_semantic_mapping,
)
from petrolab.io_utils import add_qc_columns, normalize_columns_with_map

assert canonicalize_header("SiO₂") == "SiO2"
assert canonicalize_header(" SiO2 (wt. %) ") == "SiO2"
assert canonicalize_header("Al₂O₃") == "Al2O3"
assert canonicalize_header("FeOt") == "FeOt"
assert canonicalize_header("FeO total") == "FeOt"
assert canonicalize_header("Fe2O3T") == "Fe2O3t"
assert canonicalize_header("Fe2O3 total") == "Fe2O3t"
assert canonicalize_header("Fe2O3") == "Fe2O3"
assert canonicalize_header("Na₂O wt%") == "Na2O"
assert canonicalize_header("Generation custom") == "Generation custom"

assert "total Fe as FeO" in describe_header("FeOt").warning
assert "not a measured FeO" in describe_header("FeOt").warning
assert "total Fe as Fe2O3" in describe_header("Fe2O3T").warning
assert "not a measured Fe2O3" in describe_header("Fe2O3T").warning

assert canonicalize_header("Rb ppm") == "Rb [µg/g]"
assert canonicalize_header("Rb (µg/g)") == "Rb [µg/g]"
assert canonicalize_header("Yb, мкг/г") == "Yb [µg/g]"
assert canonicalize_header("Yb µg g⁻¹") == "Yb [µg/g]"
assert canonicalize_header("La mg kg-1") == "La [µg/g]"
assert canonicalize_header("Ba ng g⁻¹") == "Ba [µg/g]"
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
assert "total Fe as FeO" in source_map["FeOt"]["warning"]
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

# Pandas may mangle a repeated Excel header as `.1`; recover the scientific meaning
# so that the conflict remains visible instead of silently becoming an unknown column.
mangled = pd.DataFrame([[50.0, 51.0, 3.0, 4.0]], columns=["FeO", "FeO.1", "Rb ppm", "Rb ppm.1"])
mangled_norm, mangled_map = normalize_columns_with_map(mangled)
assert list(mangled_norm.columns) == ["FeO", "FeO__2", "Rb [µg/g]", "Rb [µg/g]__2"]
assert "Повторяющийся" in mangled_map["FeO__2"]["warning"]
assert "Повторяющийся" in mangled_map["Rb [µg/g]__2"]["warning"]

# A duplicate oxide makes an apparently plausible sum unsafe. QC must not label it normal.
qc_conflict = add_qc_columns(
    pd.DataFrame([{"SiO2": 40.0, "MgO": 50.0, "FeO": 10.0, "FeO__2": 11.0}])
)
assert qc_conflict.loc[0, "QC суммы"] == "конфликт колонок/железа"
assert "FeO__2" in qc_conflict.loc[0, "QC химии"]

# Total Fe reported on different bases stays distinct and can be used in the oxide sum
# only when it does not overlap another Fe reporting convention in the same row.
total_fe2o3 = add_qc_columns(pd.DataFrame([{"SiO2": 50.0, "MgO": 40.0, "Fe2O3t": 10.0}]))
assert float(total_fe2o3.loc[0, "Σ оксидов"]) == 100.0
assert total_fe2o3.loc[0, "QC суммы"] == "норма"

mixed_total_basis = add_qc_columns(pd.DataFrame([
    {"SiO2": 50.0, "MgO": 40.0, "FeOt": 10.0, "Fe2O3t": None},
    {"SiO2": 50.0, "MgO": 40.0, "FeOt": None, "Fe2O3t": 10.0},
]))
assert mixed_total_basis["QC суммы"].tolist() == ["норма", "норма"]

overlapping_total_basis = add_qc_columns(pd.DataFrame([
    {"SiO2": 50.0, "MgO": 40.0, "FeOt": 10.0, "Fe2O3t": 10.0},
]))
assert overlapping_total_basis.loc[0, "QC суммы"] == "конфликт колонок/железа"
assert "total Fe" in overlapping_total_basis.loc[0, "QC железа"]

# FeO, FeOt and Fe2O3t remain semantically distinct.
iron_raw = pd.DataFrame({"FeO": [1.0], "FeOt": [2.0], "Fe2O3T": [3.0]})
iron, _ = normalize_columns_with_map(iron_raw)
assert list(iron.columns) == ["FeO", "FeOt", "Fe2O3t"]

print("column schema tests: OK")
