from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

_TMP = tempfile.TemporaryDirectory(prefix="petrolab_thermobarometry_")
os.environ["PETROLAB_DATA_DIR"] = str(Path(_TMP.name) / "data")

import pandas as pd

from petrolab.db import add_dataset, create_project, ensure_storage, load_dataset_dataframe, replace_dataset_rows, update_analysis_values
from petrolab.thermobarometry import (
    QC_INSUFFICIENT_INPUT,
    QC_PASS,
    QC_WARNING,
    calculate_putirka_2008_cpx_only_t32d,
    list_runs,
    save_run,
)


def _cpx() -> pd.DataFrame:
    return pd.DataFrame([{
        "Sample": "Cpx-1", "SiO2": 51.43, "TiO2": 0.62, "Al2O3": 3.82,
        "Cr2O3": 0.12, "FeOt": 6.41, "MgO": 15.77, "CaO": 20.91,
        "Na2O": 0.48, "K2O": 0.03,
    }])


ensure_storage()
source = _cpx()
calculated = calculate_putirka_2008_cpx_only_t32d(source, pressure_kbar=5.0, applicability_confirmed=True)
assert calculated.loc[0, "Thermobarometry status"] == QC_PASS
advisory = calculate_putirka_2008_cpx_only_t32d(source, pressure_kbar=5.0, applicability_confirmed=False)
assert advisory.loc[0, "Thermobarometry status"] == QC_WARNING
assert math.isfinite(float(advisory.loc[0, "T (°C)"]))
assert abs(float(calculated.loc[0, "T (K)"]) - 1462.890265) < 1e-5
assert abs(float(calculated.loc[0, "T (°C)"]) - 1189.740265) < 1e-5

# Negative analytical Cr cannot be a physical concentration. For Eq. 32d PetroLab
# floors only the calculation copy to zero, preserves the raw analysis, and warns.
# P2O5 is not an Eq. 32d input at all and must never block the Cpx thermometer.
negative_trace = _cpx()
negative_trace.loc[0, "Cr2O3"] = -0.01
negative_trace.loc[0, "P2O5"] = -0.04
negative_trace_before = negative_trace.copy(deep=True)
negative_trace_result = calculate_putirka_2008_cpx_only_t32d(
    negative_trace,
    pressure_kbar=5.0,
    applicability_confirmed=True,
)
zero_cr = _cpx()
zero_cr.loc[0, "Cr2O3"] = 0.0
zero_cr_result = calculate_putirka_2008_cpx_only_t32d(
    zero_cr,
    pressure_kbar=5.0,
    applicability_confirmed=True,
)
assert negative_trace_result.loc[0, "Thermobarometry status"] == QC_WARNING
assert math.isfinite(float(negative_trace_result.loc[0, "T (°C)"]))
assert abs(float(negative_trace_result.loc[0, "T (K)"]) - float(zero_cr_result.loc[0, "T (K)"])) < 1e-12
assert "Cr2O3=-0.01" in negative_trace_result.loc[0, "Thermobarometry reason"]
assert "P2O5" not in negative_trace_result.loc[0, "Thermobarometry reason"]
pd.testing.assert_frame_equal(negative_trace, negative_trace_before)

incomplete = _cpx().drop(columns=["K2O"])
blocked = calculate_putirka_2008_cpx_only_t32d(incomplete, pressure_kbar=5.0, applicability_confirmed=True)
assert blocked.loc[0, "Thermobarometry status"] == QC_INSUFFICIENT_INPUT
assert "K2O" in blocked.loc[0, "Thermobarometry reason"]

project_id = create_project("Thermobar test")
csv_path = Path(_TMP.name) / "cpx.csv"
source.to_csv(csv_path, index=False)
dataset_id = add_dataset(
    project_id=project_id, name="Cpx", mineral_key="clinopyroxene", source_filename="cpx.xlsx",
    source_sheet="Cpx", source_sha256="fixture", csv_path=str(csv_path), row_count=1,
)
replace_dataset_rows(dataset_id, source, source_rows=[2])
stored_source = load_dataset_dataframe(dataset_id, include_meta=True)
stored_result = calculate_putirka_2008_cpx_only_t32d(stored_source, pressure_kbar=5.0, applicability_confirmed=True)
run = save_run(
    project_id, method_id="putirka_2008_cpx_only_t32d", source_dataframe=stored_source,
    results_dataframe=stored_result, assumptions={"pressure_kbar": 5.0},
)
assert run.is_current and len(run.input_analysis_ids) == 1
history = list_runs(project_id)
assert len(history) == 1 and history[0].is_current

analysis_id = str(stored_source.loc[0, "_analysis_id"])
update_analysis_values([{
    "analysis_id": analysis_id, "dataset_id": dataset_id, "column_name": "TiO2",
    "old_value": 0.62, "new_value": 0.63,
}])
assert not list_runs(project_id)[0].is_current

assert math.isfinite(float(calculated.loc[0, "a_En"]))
print("thermobarometry tests: OK")
