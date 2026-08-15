from __future__ import annotations

import math
import os
import tempfile
from pathlib import Path

_TMP = tempfile.TemporaryDirectory(prefix="petrolab_thermodynamics_")
os.environ["PETROLAB_DATA_DIR"] = str(Path(_TMP.name) / "data")

import pandas as pd

from petrolab.db import add_dataset, create_project, ensure_storage, load_dataset_dataframe, replace_dataset_rows, update_analysis_values
from petrolab.thermodynamics import (
    FERRY_WATSON_2007_TI_ZIRCON,
    LOUCKS_2020_ZIRCON_DFMQ,
    MUTCH_2016_AMP_BAROMETER,
    PUTIRKA_2008_OL_LIQ_EQ22,
    PUTIRKA_2016_AMP_EQ5,
    calculate_method,
    list_thermodynamic_runs,
    save_thermodynamic_run,
    thermodynamic_records_for_analysis,
)
from petrolab.thermobarometry import QC_PASS, QC_WARNING


ensure_storage()

# Ferry & Watson (2007): at unit activities, Ti=10 ppm gives an exactly reproducible equation result.
zircon = pd.DataFrame([{"Sample": "Z1", "Ti [µg/g]": 10.0, "Ce [µg/g]": 100.0, "Ui [µg/g]": 50.0}])
ti_zrn = calculate_method(
    FERRY_WATSON_2007_TI_ZIRCON.method_id,
    zircon,
    assumptions={"a_sio2": 1.0, "a_tio2": 1.0},
)
expected_tk = 4800.0 / (5.711 - math.log10(10.0))
assert abs(float(ti_zrn.loc[0, "T (K)"]) - expected_tk) < 1e-9
assert ti_zrn.loc[0, "Thermodynamic status"] == QC_PASS

# Loucks et al. (2020): Ui is explicit and the published ΔFMQ equation is reproduced.
oxy = calculate_method(LOUCKS_2020_ZIRCON_DFMQ.method_id, zircon)
expected_dfmq = 3.998 * math.log10(100.0 / math.sqrt(50.0 * 10.0)) + 2.284
assert abs(float(oxy.loc[0, "ΔFMQ"]) - expected_dfmq) < 1e-9
assert oxy.loc[0, "Thermodynamic status"] == QC_PASS

# Measured U is never silently treated as Ui. Explicit opt-in produces WARNING, not PASS.
zircon_measured_u = pd.DataFrame([{"Ti [µg/g]": 10.0, "Ce [µg/g]": 100.0, "U [µg/g]": 50.0}])
blocked = calculate_method(LOUCKS_2020_ZIRCON_DFMQ.method_id, zircon_measured_u)
assert math.isnan(float(blocked.loc[0, "ΔFMQ"])) if "ΔFMQ" in blocked.columns else True
allowed = calculate_method(
    LOUCKS_2020_ZIRCON_DFMQ.method_id,
    zircon_measured_u,
    assumptions={"allow_measured_u_as_initial": True},
)
assert allowed.loc[0, "Thermodynamic status"] == QC_WARNING

# Amphibole-only methods use the same 23-O stoichiometric basis but retain their separate applicability contracts.
amphibole = pd.DataFrame([{
    "Sample": "A1", "SiO2": 45.0, "TiO2": 1.6, "Al2O3": 10.5, "FeOt": 12.0,
    "MnO": 0.2, "MgO": 14.0, "CaO": 11.5, "Na2O": 2.2, "K2O": 1.0,
}])
amp_t = calculate_method(
    PUTIRKA_2016_AMP_EQ5.method_id,
    amphibole,
    assumptions={"applicability_confirmed": True},
)
assert amp_t.loc[0, "Thermodynamic status"] == QC_PASS
assert math.isfinite(float(amp_t.loc[0, "T (°C)"]))
amp_p = calculate_method(
    MUTCH_2016_AMP_BAROMETER.method_id,
    amphibole,
    assumptions={"assemblage_confirmed": False},
)
assert amp_p.loc[0, "Thermodynamic status"] == QC_WARNING
assert math.isfinite(float(amp_p.loc[0, "P (kbar)"]))

# Olivine–melt Eq. 22 uses one explicit representative melt and never auto-matches pairs.
olivine = pd.DataFrame([{
    "Sample": "Ol1", "SiO2": 40.2, "FeOt": 11.0, "MnO": 0.18,
    "MgO": 47.8, "CaO": 0.2, "NiO": 0.25,
}])
melt = {
    "SiO2": 49.5, "TiO2": 1.2, "Al2O3": 15.5, "FeOt": 9.0, "MnO": 0.15,
    "MgO": 7.5, "CaO": 10.5, "Na2O": 3.2, "K2O": 1.1, "H2O": 2.0,
}
ol_liq = calculate_method(
    PUTIRKA_2008_OL_LIQ_EQ22.method_id,
    olivine,
    assumptions={"pressure_kbar": 3.0, "equilibrium_confirmed": True},
    melt=melt,
)
assert ol_liq.loc[0, "Thermodynamic status"] == QC_PASS
assert math.isfinite(float(ol_liq.loc[0, "T (°C)"]))
assert float(ol_liq.loc[0, "DMg ol/melt"]) > 0

# Saved results are tied to immutable analysis IDs and become stale after source chemistry changes.
project_id = create_project("Thermodynamic test")
source = pd.DataFrame([{"Sample": "Z1", "Ti [µg/g]": 10.0, "Ce [µg/g]": 100.0, "Ui [µg/g]": 50.0}])
csv_path = Path(_TMP.name) / "zircon.csv"
source.to_csv(csv_path, index=False)
dataset_id = add_dataset(
    project_id=project_id, name="Zircon", mineral_key="zircon", source_filename="zircon.xlsx",
    source_sheet="Zrn", source_sha256="fixture", csv_path=str(csv_path), row_count=1,
)
replace_dataset_rows(dataset_id, source, source_rows=[2])
stored = load_dataset_dataframe(dataset_id, include_meta=True)
result = calculate_method(
    FERRY_WATSON_2007_TI_ZIRCON.method_id,
    stored,
    assumptions={"a_sio2": 1.0, "a_tio2": 1.0},
)
run = save_thermodynamic_run(
    project_id,
    method_id=FERRY_WATSON_2007_TI_ZIRCON.method_id,
    source_dataframe=stored,
    results_dataframe=result,
    assumptions={"a_sio2": 1.0, "a_tio2": 1.0},
)
assert run.is_current
analysis_id = str(stored.loc[0, "_analysis_id"])
records = thermodynamic_records_for_analysis(project_id, analysis_id)
assert records and records[0]["Актуальность"] == "Актуален"
update_analysis_values([{
    "analysis_id": analysis_id, "dataset_id": dataset_id, "column_name": "Ti [µg/g]",
    "old_value": 10.0, "new_value": 11.0,
}])
assert not list_thermodynamic_runs(project_id)[0].is_current

print("thermodynamics tests: OK")
