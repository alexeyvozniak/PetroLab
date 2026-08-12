import math
import pandas as pd

from petrolab.minerals.base import MineralModule
from petrolab.minerals.formulae import calculate_formula


def near(a, b, tol=0.02):
    assert math.isfinite(float(a))
    assert abs(float(a) - b) <= tol, (a, b)


# Synthetic ideal endmembers, wt.% calculated from stoichiometry closely enough
# to test normalization and endmember arithmetic.
ol = pd.DataFrame([{"SiO2": 42.73, "MgO": 57.27, "FeO": 0.0}])
r = calculate_formula(ol, "olivine", "ol_4o_fe2").data.iloc[0]
near(r["apfu_Si"], 1.0)
near(r["apfu_Mg"], 2.0)
near(r["Fo"], 100.0, 0.05)

# FeOt (total Fe expressed as FeO) is a valid FeO-equivalent input when no
# separate FeO/Fe2O3 split is supplied.
ol_feo = pd.DataFrame([{"SiO2": 40.0, "MgO": 50.0, "FeO": 10.0}])
ol_feot = pd.DataFrame([{"SiO2": 40.0, "MgO": 50.0, "FeOt": 10.0}])
r_feo = calculate_formula(ol_feo, "olivine", "ol_4o_fe2").data.iloc[0]
r_feot = calculate_formula(ol_feot, "olivine", "ol_4o_fe2").data.iloc[0]
near(r_feot["apfu_Fe2"], float(r_feo["apfu_Fe2"]), 1e-8)
near(r_feot["Fo"], float(r_feo["Fo"]), 1e-8)

# Total Fe plus a separate Fe2O3 column but no FeO split is ambiguous: the
# engine must refuse to double-count/guess ferric iron.
ambiguous_fe = pd.DataFrame([{"SiO2": 40.0, "MgO": 48.0, "FeOt": 10.0, "Fe2O3": 2.0}])
try:
    calculate_formula(ambiguous_fe, "olivine", "ol_4o_fe2")
except ValueError as exc:
    assert "FeOt" in str(exc) and "Fe2O3" in str(exc)
else:
    raise AssertionError("FeOt + Fe2O3 without FeO must be rejected")

# Import intentionally preserves duplicate chemical inputs as technical __2 columns.
# Formulae and base Mg# must not silently choose the first one.
duplicate_chemistry = pd.DataFrame([
    {"SiO2": 40.0, "MgO": 48.0, "FeO": 10.0, "FeO__2": 11.0}
])
try:
    calculate_formula(duplicate_chemistry, "olivine", "ol_4o_fe2")
except ValueError as exc:
    assert "FeO__2" in str(exc)
else:
    raise AssertionError("Duplicate formula inputs must block structural recalculation")

base_module = MineralModule("test", "test", "test", "test")
base_duplicate = base_module.calculate(duplicate_chemistry)
assert "Mg#" not in base_duplicate.columns
assert "QC Mg#" in base_duplicate.columns

fsp = pd.DataFrame([{"SiO2": 68.74, "Al2O3": 19.44, "Na2O": 11.82}])
r = calculate_formula(fsp, "feldspar", "fsp_8o").data.iloc[0]
near(r["Ab"], 100.0, 0.05)

px = pd.DataFrame([{"SiO2": 55.49, "MgO": 18.61, "CaO": 25.90, "FeO": 0.0}])
r = calculate_formula(px, "clinopyroxene", "px_6o_fe2").data.iloc[0]
near(r["Wo"], 50.0, 0.2)
near(r["En"], 50.0, 0.2)

mica = pd.DataFrame([{"SiO2": 45.1481626, "Al2O3": 12.7693084, "MgO": 30.2856306, "K2O": 11.7968984, "F": 0.0, "Cl": 0.0}])
r = calculate_formula(mica, "mica", "mica_rieder_11o").data.iloc[0]
near(r["apfu_Si"], 3.0, 0.05)
near(r["apfu_K"], 1.0, 0.05)
near(r["apfu_Mg"], 3.0, 0.08)
near(r["apfu_OH_max"], 2.0, 0.02)

# Routine EPMA tables frequently omit F and/or Cl entirely. Missing halogens
# must behave as zero for OH_max and must not cause a scalar .clip() failure.
mica_no_hal = mica.drop(columns=["F", "Cl"])
r_no_hal = calculate_formula(mica_no_hal, "mica", "mica_rieder_11o").data.iloc[0]
near(r_no_hal["apfu_OH_max"], 2.0, 0.02)
assert "F" not in r_no_hal.index
assert "Cl" not in r_no_hal.index

# Ideal nepheline NaAlSiO4 on 32 O should return 100 mol% Ne.
ne = pd.DataFrame([{"SiO2": 42.306, "Al2O3": 35.91, "Na2O": 21.784}])
r = calculate_formula(ne, "nepheline", "ne_henderson32").data.iloc[0]
near(r["T_sum_32O"], 16.0, 0.05)
near(r["Ne_mol%"], 100.0, 0.2)
near(r["Qxs_mol%"], 0.0, 0.2)

# Ideal pyrope Mg3Al2Si3O12.
grt = pd.DataFrame([{"SiO2": 44.704, "Al2O3": 25.298, "MgO": 29.998}])
r = calculate_formula(grt, "garnet", "grt_12o_fe2").data.iloc[0]
near(r["Prp"], 100.0, 0.3)

print("formula tests: OK")
