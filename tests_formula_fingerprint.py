from __future__ import annotations

import json

from petrolab.analysis_identity import source_row_fingerprint
from petrolab.derived import _formula_row_current

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

print("formula fingerprint tests: OK")
