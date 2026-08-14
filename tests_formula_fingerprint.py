from __future__ import annotations

import json

import numpy as np
import pandas as pd

from petrolab.analysis_identity import source_row_fingerprint
from petrolab.derived import _formula_row_current
from petrolab.services.formula_service import _restore_missing_semantics

source_payload = {"Sample": "M1", "SiO2": 40.0, "Al2O3": 12.0}
fingerprint = source_row_fingerprint(source_payload)

touched_row = {
    "derived_json": json.dumps({"__source_fingerprint__": fingerprint, "apfu_Si": 3.1}),
    "data_json": json.dumps(source_payload),
    "source_updated_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2099-01-01T00:00:00+00:00",
}
assert _formula_row_current(touched_row)

changed_row = dict(touched_row)
changed_row["data_json"] = json.dumps({**source_payload, "Al2O3": 15.0})
assert not _formula_row_current(changed_row)

legacy_current = {
    "derived_json": json.dumps({"apfu_Si": 3.1}),
    "data_json": json.dumps(source_payload),
    "source_updated_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
}
assert _formula_row_current(legacy_current)

# A blank F/Cl cell in an explicitly supplied analytical column is unknown chemistry,
# not measured zero. OH-dependent outputs must therefore stay undefined for that row.
original = pd.DataFrame({"P2O5": [42.0], "CaO": [55.0], "F": [np.nan], "Cl": [0.2]})
calculated = original.copy()
calculated["apfu_F"] = 0.0
calculated["apfu_Cl"] = 0.05
calculated["apfu_OH_est"] = 0.95
calculated["apfu_OH_max"] = 1.0
calculated["QC_Z_site"] = "норма"
restored = _restore_missing_semantics(calculated, original, "apatite")
assert pd.isna(restored.loc[0, "apfu_F"])
assert pd.isna(restored.loc[0, "apfu_OH_est"])
assert pd.isna(restored.loc[0, "apfu_OH_max"])
assert restored.loc[0, "QC_Z_site"] == "не рассчитано: пропуск F/Cl"

print("formula fingerprint and row-semantics tests: OK")
