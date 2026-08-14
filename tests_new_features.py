from __future__ import annotations

import gc
import json
import math
import os
import tempfile
import time
from pathlib import Path

# PETROLAB_DATA_DIR must be fixed before importing the package because the database path
# is resolved during module import.
_TMP = tempfile.TemporaryDirectory(prefix="petrolab_new_features_")
_ROOT = Path(_TMP.name)
os.environ["PETROLAB_DATA_DIR"] = str(_ROOT / "data")

import pandas as pd

from petrolab.analysis_groups import (
    WORK_GROUP_COLUMN,
    attach_work_groups,
    clear_work_group,
    set_work_group,
)
from petrolab.db import (
    _utcnow,
    add_dataset,
    connect,
    create_project,
    ensure_storage,
    load_dataset_dataframe,
    replace_dataset_rows,
)
from petrolab.derived import formula_status, load_unified_with_derived, save_formula_results
from petrolab.interactive_plotting import build_interactive_scatter, selected_analysis_ids
from petrolab.measurement_semantics import apply_measurement_overrides
from petrolab.services.formula_service import FE2O3T_TO_FEOT, calculate_formula_safe


def near(a, b, tol=1e-8):
    assert math.isfinite(float(a))
    assert abs(float(a) - float(b)) <= tol, (a, b)


def cleanup_tempdir() -> None:
    """Release delayed SQLite/Pandas objects before removing the Windows temp database.

    The retry is deliberately bounded: a genuinely leaked connection must still fail CI.
    """
    last_error: PermissionError | None = None
    for attempt in range(5):
        gc.collect()
        try:
            _TMP.cleanup()
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.1 * (attempt + 1))
    assert last_error is not None
    raise last_error


ensure_storage()

# Reporting basis must not alter the number of Fe atoms used by the formula.
feo_basis = pd.DataFrame([{"SiO2": 40.0, "MgO": 50.0, "FeOt": 10.0}])
fe2o3_basis = pd.DataFrame(
    [{"SiO2": 40.0, "MgO": 50.0, "Fe2O3t": 10.0 / FE2O3T_TO_FEOT}]
)
feo_calculation = calculate_formula_safe(feo_basis, "olivine", "ol_4o_fe2")
fe2o3_calculation = calculate_formula_safe(fe2o3_basis, "olivine", "ol_4o_fe2")
feo_result = feo_calculation.data.iloc[0]
fe2o3_result = fe2o3_calculation.data.iloc[0]
near(feo_result["apfu_Fe2"], fe2o3_result["apfu_Fe2"])
near(feo_result["Fo"], fe2o3_result["Fo"])
assert "Fe2O3t" in fe2o3_calculation.data.columns
assert "FeOt" not in fe2o3_calculation.data.columns
assert "не задаёт Fe³⁺/Fe²⁺" in fe2o3_calculation.note_ru

# Fe2O3t is total Fe reporting basis and cannot coexist with another Fe source in one row.
try:
    calculate_formula_safe(
        pd.DataFrame([{"SiO2": 40.0, "MgO": 50.0, "FeO": 5.0, "Fe2O3t": 5.0}]),
        "olivine",
        "ol_4o_fe2",
    )
except ValueError as exc:
    assert "Fe2O3t" in str(exc) and "FeO" in str(exc)
else:
    raise AssertionError("Fe2O3t plus FeO must be rejected")

# User-confirmed semantics are stored by renaming Fe2O3 to the explicit Fe2O3t role.
raw = pd.DataFrame({"Fe2O3": [11.0], "SiO2": [40.0]})
column_map = {
    "Fe2O3": {"original": "Fe2O3"},
    "SiO2": {"original": "SiO2"},
}
renamed, mapped, stored = apply_measurement_overrides(
    raw, column_map, {"Fe2O3": "Fe2O3t"}
)
assert "Fe2O3t" in renamed.columns and "Fe2O3" not in renamed.columns
assert stored == {"Fe2O3": "Fe2O3t"}
assert mapped["__schema__"]["measurement"] == stored

# Persisted formula fields are current only while the source analysis version is unchanged.
project_id = create_project("Derived formula test")
frame = pd.DataFrame(
    {
        "Sample": ["M1", "M2"],
        "SiO2": [40.0, 41.0],
        "Al2O3": [12.0, 13.0],
        "TiO2": [3.0, 4.0],
        "MgO": [20.0, 19.0],
        "FeO": [8.0, 9.0],
        "K2O": [10.0, 10.0],
        "Rb [µg/g]": [150.0, 210.0],
    }
)
csv_path = _ROOT / "mica.csv"
frame.to_csv(csv_path, index=False)
dataset_id = add_dataset(
    project_id=project_id,
    name="Mica",
    mineral_key="mica",
    source_filename="mica.xlsx",
    source_sheet="Mica",
    source_sha256="test",
    csv_path=str(csv_path),
    row_count=len(frame),
    source_path="",
    source_kind="upload",
    header_row=1,
    column_map={},
    sync_enabled=False,
)
replace_dataset_rows(dataset_id, frame, source_rows=[2, 3])

source = load_dataset_dataframe(dataset_id, include_meta=True)
result = calculate_formula_safe(source, "mica", "mica_rieder_11o")
saved = save_formula_results(
    dataset_id=dataset_id,
    mineral_key="mica",
    method_id="mica_rieder_11o",
    method_title="IMA 11 O",
    source_dataframe=source,
    result_dataframe=result.data,
)
assert "apfu_AlIV" in saved.derived_columns

unified = load_unified_with_derived(project_id, [dataset_id])
assert "apfu_AlIV" in unified.columns
assert unified["apfu_AlIV"].notna().all()
assert "Rb [µg/g]" in unified.columns

first_id = str(source.iloc[0]["_analysis_id"])
second_id = str(source.iloc[1]["_analysis_id"])

# Local working groups are keyed by immutable analysis ID and never alter source data_json.
assert set_work_group([first_id], "xenocryst candidate") == 1
grouped = attach_work_groups(unified)
assert grouped.loc[grouped["_analysis_id"].astype(str) == first_id, WORK_GROUP_COLUMN].iloc[0] == "xenocryst candidate"
assert grouped.loc[grouped["_analysis_id"].astype(str) == second_id, WORK_GROUP_COLUMN].iloc[0] == ""

# Plotly diagnostic figures carry analysis IDs in customdata, so lasso/click selection
# survives sorting/grouping and can be translated back to the exact analytical row.
interactive = build_interactive_scatter(
    grouped,
    "Rb [µg/g]",
    "apfu_AlIV",
    WORK_GROUP_COLUMN,
    x_label="Rb, ppm",
    y_label="AlIV, apfu",
)
custom_ids = {
    str(point[0])
    for trace in interactive.data
    for point in trace.customdata
}
assert {first_id, second_id}.issubset(custom_ids)
selection_event = {
    "selection": {
        "points": [
            {"customdata": [first_id, "M1"]},
            {"customdata": [second_id, "M2"]},
        ]
    }
}
assert selected_analysis_ids(selection_event) == [first_id, second_id]
assert clear_work_group([first_id]) == 1
assert attach_work_groups(unified)[WORK_GROUP_COLUMN].eq("").all()

with connect() as con:
    row = con.execute(
        "SELECT data_json FROM analysis_rows WHERE analysis_id=?", (first_id,)
    ).fetchone()
    payload = json.loads(row["data_json"])
    payload["Al2O3"] = 15.0
    con.execute(
        "UPDATE analysis_rows SET data_json=?, updated_at=? WHERE analysis_id=?",
        (json.dumps(payload, ensure_ascii=False), _utcnow(), first_id),
    )
    con.commit()

status = formula_status(dataset_id)
assert status.current_rows == 1
assert status.stale_rows == 1
refreshed = load_unified_with_derived(project_id, [dataset_id])
changed = refreshed[refreshed["_analysis_id"].astype(str) == first_id].iloc[0]
unchanged = refreshed[refreshed["_analysis_id"].astype(str) != first_id].iloc[0]
assert pd.isna(changed["apfu_AlIV"])
assert pd.notna(unchanged["apfu_AlIV"])

cleanup_tempdir()
print("new feature integration tests: OK")
