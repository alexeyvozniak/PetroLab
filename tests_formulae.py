import math
import pandas as pd

from petrolab.minerals.base import MineralModule
from petrolab.minerals.formulae import calculate_formula


def near(a, b, tol=0.02):
    assert math.isfinite(float(a))
    assert abs(float(a) - b) <= tol, (a, b)


ol = pd.DataFrame([{"SiO2": 42.73, "MgO": 57.27, "FeO": 0.0}])
r = calculate_formula(ol, "olivine", "ol_4o_fe2").data.iloc[0]
near(r["apfu_Si"], 1.0); near(r["apfu_Mg"], 2.0); near(r["Fo"], 100.0, 0.05)

ol_feo = pd.DataFrame([{"SiO2": 40.0, "MgO": 50.0, "FeO": 10.0}])
ol_feot = pd.DataFrame([{"SiO2": 40.0, "MgO": 50.0, "FeOt": 10.0}])
r_feo = calculate_formula(ol_feo, "olivine", "ol_4o_fe2").data.iloc[0]
r_feot = calculate_formula(ol_feot, "olivine", "ol_4o_fe2").data.iloc[0]
near(r_feot["apfu_Fe2"], float(r_feo["apfu_Fe2"]), 1e-8); near(r_feot["Fo"], float(r_feo["Fo"]), 1e-8)

mixed_fe = pd.DataFrame([
    {"SiO2": 40.0, "MgO": 50.0, "FeO": 10.0, "FeOt": None},
    {"SiO2": 40.0, "MgO": 50.0, "FeO": None, "FeOt": 10.0},
])
mixed_result = calculate_formula(mixed_fe, "olivine", "ol_4o_fe2").data
near(mixed_result.iloc[0]["apfu_Fe2"], float(r_feo["apfu_Fe2"]), 1e-8)
near(mixed_result.iloc[1]["apfu_Fe2"], float(r_feo["apfu_Fe2"]), 1e-8)

mixed_base = MineralModule("test", "test", "test", "test").calculate(mixed_fe)
assert mixed_base["Mg#"].notna().all()

for bad in (
    pd.DataFrame([{"SiO2": 40.0, "MgO": 50.0, "FeO": 9.0, "FeOt": 10.0}]),
    pd.DataFrame([{"SiO2": 40.0, "MgO": 48.0, "FeOt": 10.0, "Fe2O3": 2.0}]),
):
    try:
        calculate_formula(bad, "olivine", "ol_4o_fe2")
    except ValueError:
        pass
    else:
        raise AssertionError("Ambiguous Fe input must be rejected")

total_fe2o3_input = pd.DataFrame([{"SiO2": 40.0, "MgO": 50.0, "Fe2O3t": 10.0}])
try:
    calculate_formula(total_fe2o3_input, "olivine", "ol_4o_fe2")
except ValueError as exc:
    assert "Fe2O3t" in str(exc)
else:
    raise AssertionError("Fe2O3t must not be silently ignored")

duplicate_chemistry = pd.DataFrame([{"SiO2": 40.0, "MgO": 48.0, "FeO": 10.0, "FeO__2": 11.0}])
try:
    calculate_formula(duplicate_chemistry, "olivine", "ol_4o_fe2")
except ValueError:
    pass
else:
    raise AssertionError("Duplicate formula inputs must block recalculation")

fsp = pd.DataFrame([{"SiO2": 68.74, "Al2O3": 19.44, "Na2O": 11.82}])
near(calculate_formula(fsp, "feldspar", "fsp_8o").data.iloc[0]["Ab"], 100.0, 0.05)

px = pd.DataFrame([{"SiO2": 55.49, "MgO": 18.61, "CaO": 25.90, "FeO": 0.0}])
r = calculate_formula(px, "clinopyroxene", "px_6o_fe2").data.iloc[0]
near(r["Wo"], 50.0, 0.2); near(r["En"], 50.0, 0.2)

# Explicit ferric Fe must not be silently overwritten by a Droop estimate.
px_measured_fe3 = pd.DataFrame([{
    "SiO2": 50.0, "MgO": 15.0, "CaO": 20.0, "FeO": 6.0, "Fe2O3": 2.0,
}])
try:
    calculate_formula(px_measured_fe3, "clinopyroxene", "px_morimoto_droop")
except ValueError as exc:
    assert "Droop" in str(exc) and "Fe3" in str(exc)
else:
    raise AssertionError("Droop must refuse independently supplied Fe3+")

mica = pd.DataFrame([{"SiO2": 45.1481626, "Al2O3": 12.7693084, "MgO": 30.2856306, "K2O": 11.7968984, "F": 0.0, "Cl": 0.0}])
r = calculate_formula(mica, "mica", "mica_rieder_11o").data.iloc[0]
near(r["apfu_Si"], 3.0, 0.05); near(r["apfu_K"], 1.0, 0.05); near(r["apfu_Mg"], 3.0, 0.08); near(r["apfu_OH_max"], 2.0, 0.02)

# Mica OH_max remains a maximum when F/Cl are absent; this is not species classification.
mica_no_hal = mica.drop(columns=["F", "Cl"])
r_no_hal = calculate_formula(mica_no_hal, "mica", "mica_rieder_11o").data.iloc[0]
near(r_no_hal["apfu_OH_max"], 2.0, 0.02)

ne = pd.DataFrame([{"SiO2": 42.306, "Al2O3": 35.91, "Na2O": 21.784}])
r = calculate_formula(ne, "nepheline", "ne_henderson32").data.iloc[0]
near(r["T_sum_32O"], 16.0, 0.05); near(r["Ne_mol%"], 100.0, 0.2)

grt = pd.DataFrame([{"SiO2": 44.704, "Al2O3": 25.298, "MgO": 29.998}])
near(calculate_formula(grt, "garnet", "grt_12o_fe2").data.iloc[0]["Prp"], 100.0, 0.3)

# Apatite without both halogens must not manufacture an OH estimate.
apt_missing_hal = pd.DataFrame([{"P2O5": 42.0, "CaO": 55.0}])
apt_missing = calculate_formula(apt_missing_hal, "apatite", "ap_ketcham25").data.iloc[0]
assert pd.isna(apt_missing["apfu_OH_est"])
assert "не полностью" in apt_missing["QC_Z_site"]

apt_measured = pd.DataFrame([{"P2O5": 42.0, "CaO": 55.0, "F": 3.0, "Cl": 0.0}])
apt = calculate_formula(apt_measured, "apatite", "ap_ketcham25").data.iloc[0]
assert math.isfinite(float(apt["apfu_OH_est"]))
assert apt["OH_est_basis"] == "F и Cl измерены"

# Carbonate FeOt must contribute exactly as FeO-equivalent total Fe.
carbonate_feo = pd.DataFrame([{"CaO": 30.0, "MgO": 15.0, "FeO": 10.0}])
carbonate_feot = pd.DataFrame([{"CaO": 30.0, "MgO": 15.0, "FeOt": 10.0}])
carb_feo = calculate_formula(carbonate_feo, "carbonate", "carb_1cat").data.iloc[0]
carb_feot = calculate_formula(carbonate_feot, "carbonate", "carb_1cat").data.iloc[0]
near(carb_feot["apfu_Fe2"], float(carb_feo["apfu_Fe2"]), 1e-8)
near(carb_feot["X_Fe2"], float(carb_feo["X_Fe2"]), 1e-8)

print("formula tests: OK")
