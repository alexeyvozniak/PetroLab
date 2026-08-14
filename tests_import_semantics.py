from __future__ import annotations

import inspect

import pandas as pd

from petrolab.measurement_semantics import apply_measurement_overrides
from petrolab.services.import_service import import_linked_sheets, import_uploaded_sheets


# Current UI passes per-sheet settings; backend must keep this contract.
for function in (import_linked_sheets, import_uploaded_sheets):
    parameters = inspect.signature(function).parameters
    assert "header_rows" in parameters
    assert "mineral_keys" in parameters

# FeO can be explicitly confirmed as total Fe reported on an FeO basis.
source_map = {
    "FeO": {"original": "FeO", "quantity_kind": "oxide"},
    "__schema__": {"semantic": {"Point": "Spot"}},
}
frame = pd.DataFrame({"FeO": [12.5], "MgO": [10.0]})
out, mapped, stored = apply_measurement_overrides(frame, source_map, {"FeO": "FeOt"})
assert "FeOt" in out.columns and "FeO" not in out.columns
assert stored == {"FeO": "FeOt"}
assert mapped["__schema__"]["semantic"] == {"Point": "Spot"}
assert mapped["__schema__"]["measurement"] == {"FeO": "FeOt"}
assert source_map["__schema__"] == {"semantic": {"Point": "Spot"}}, "nested source metadata was mutated"

# Bare Fe2O3 is scientifically ambiguous and must never silently become ferric or total Fe.
fe3 = pd.DataFrame({"Fe2O3": [8.0]})
try:
    apply_measurement_overrides(
        fe3,
        {"Fe2O3": {"original": "Fe2O3", "quantity_kind": "oxide"}, "__schema__": {}},
        {},
    )
except ValueError as exc:
    assert "явно подтвердить" in str(exc)
else:
    raise AssertionError("Bare Fe2O3 was accepted without explicit semantics")

# Two physical columns normalised to the same scientific component must not be resolved by order.
duplicate = pd.DataFrame({"La [µg/g]": [100.0], "La [µg/g]__2": [101.0]})
try:
    apply_measurement_overrides(
        duplicate,
        {
            "La [µg/g]": {"original": "La ppm", "quantity_kind": "trace_element"},
            "La [µg/g]__2": {"original": "La ug/g", "quantity_kind": "trace_element"},
            "__schema__": {},
        },
        {},
    )
except ValueError as exc:
    assert "конфликтующие научные колонки" in str(exc)
else:
    raise AssertionError("Duplicate canonical chemistry was accepted")

print("import semantics tests: OK")
