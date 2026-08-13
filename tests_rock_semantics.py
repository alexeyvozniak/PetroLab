from __future__ import annotations

import numpy as np
import pandas as pd

import petrolab.services.rock_service as rock_service


# Separately measured ferric iron alone is not total/ferrous Fe and cannot define Mg#.
assert np.isnan(rock_service.whole_rock_mg_number({"MgO": 10.0, "Fe2O3": 8.0}))

# Two physical columns that normalize to the same analyte are ambiguous and must block.
duplicate_row = pd.Series({"La ppm": 100.0, "La [µg/g]": 110.0})
try:
    rock_service.canonicalize_rock_row(duplicate_row)
except ValueError as exc:
    assert "La [µg/g]" in str(exc)
else:
    raise AssertionError("Duplicate canonical whole-rock chemistry must block import")

# Verify update semantics without opening SQLite: the service must merge the incoming
# partial composition with existing chemistry before passing it to the transactional repository.
original_list_rocks = rock_service.list_rocks
original_existing = rock_service._existing_composition_with_units
original_apply = rock_service.apply_rock_import_batch
captured: dict[str, object] = {}

try:
    rock_service.list_rocks = lambda project_id=None: [{"id": 7, "name": "R1"}]
    rock_service._existing_composition_with_units = lambda rock_id: (
        {"SiO2": 44.0, "La [µg/g]": 120.0},
        {"SiO2": "wt%", "La [µg/g]": "µg/g"},
    )

    def fake_apply(project_id, prepared_rows, **kwargs):
        rows = list(prepared_rows)
        captured["rows"] = rows
        return (), (7,), ()

    rock_service.apply_rock_import_batch = fake_apply
    result = rock_service.import_rocks_wide(
        pd.DataFrame({"Rock": ["R1"], "SiO2": [46.0]}),
        project_id=1,
        name_column="Rock",
        on_conflict="update",
    )
    assert result.updated_ids == (7,)
    prepared = captured["rows"][0]
    assert prepared["composition"]["SiO2"] == 46.0
    assert prepared["composition"]["La [µg/g]"] == 120.0
    assert prepared["units"]["La [µg/g]"] == "µg/g"
finally:
    rock_service.list_rocks = original_list_rocks
    rock_service._existing_composition_with_units = original_existing
    rock_service.apply_rock_import_batch = original_apply

print("rock semantics tests: OK")
