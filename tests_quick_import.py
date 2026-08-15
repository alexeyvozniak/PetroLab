from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = tempfile.TemporaryDirectory(prefix="petrolab_quick_import_")
os.environ["PETROLAB_DATA_DIR"] = str(Path(_TMP.name) / "data")

from petrolab.services.import_service import inspect_uploaded_sheet, preview_uploaded_source
from petrolab.ui.pages.quick_import import _safe_automatic_mapping


safe_csv = (
    "Sample,Point,SiO2,Al2O3,FeOt,MgO\n"
    "PG-1,1,40.1,14.2,8.5,20.0\n"
).encode("utf-8")
safe_preview = inspect_uploaded_sheet(safe_csv, "safe.csv", "", 1)
safe_mapping, safe_blockers = _safe_automatic_mapping(safe_preview)
assert not safe_blockers, safe_blockers
assert safe_mapping.get("Sample") == "Sample"
assert safe_mapping.get("Point") == "Point"
safe_normalized = preview_uploaded_source(
    safe_csv,
    "safe.csv",
    "",
    1,
    "generic",
    safe_mapping,
    {},
)
assert len(safe_normalized) == 1
assert "FeOt" in safe_normalized.columns

ambiguous_fe = (
    "Sample,Point,SiO2,FeO,MgO\n"
    "PG-1,1,40.1,8.5,20.0\n"
).encode("utf-8")
fe_preview = inspect_uploaded_sheet(ambiguous_fe, "ambiguous.csv", "", 1)
_, fe_blockers = _safe_automatic_mapping(fe_preview)
assert any("FeO" in reason for reason in fe_blockers), fe_blockers

duplicate_csv = (
    "Sample,SiO2,SiO₂,MgO\n"
    "PG-1,40.1,40.2,20.0\n"
).encode("utf-8")
duplicate_preview = inspect_uploaded_sheet(duplicate_csv, "duplicate.csv", "", 1)
_, duplicate_blockers = _safe_automatic_mapping(duplicate_preview)
assert duplicate_blockers, "duplicate scientific columns must block quick import"

print("quick import tests: OK")
