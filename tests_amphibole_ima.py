import math

import pandas as pd

from petrolab.minerals.amphibole_ima import attach_amphibole_ima_diagnostics
from petrolab.minerals.classification import FIELD_COL, SPECIES_COL, attach_mineral_classification
from petrolab.services.formula_service import calculate_formula_safe
from petrolab.visualization_presets import SCIENTIFIC_PLOT_PRESETS


def row(*, explicit_fe3=True, **apfu):
    data = {f"apfu_{key}": value for key, value in apfu.items()}
    if explicit_fe3:
        data["Fe2O3"] = 0.0
    return data


def check(data, subgroup, root_text, a_plus, c_plus):
    result = attach_amphibole_ima_diagnostics(pd.DataFrame([data])).iloc[0]
    assert result["amp_B_subgroup"] == subgroup, result.to_dict()
    assert root_text in result["amp_root_field"], result.to_dict()
    assert result["amp_site_QC"] == "норма", result.to_dict()
    assert math.isclose(float(result["amp_A_plus"]), a_plus, abs_tol=1e-9)
    assert math.isclose(float(result["amp_C_plus"]), c_plus, abs_tol=1e-9)
    return result


# Idealized charge-node compositions are used only to test site allocation and subgroup/root screening.
tr = check(row(Si=8, Mg=5, Ca=2), "calcium", "tremolite", 0, 0)
assert math.isclose(float(tr["amp_T_Si"]), 8.0)
assert math.isclose(float(tr["amp_C_Mg"]), 5.0)
assert math.isclose(float(tr["amp_B_Ca"]), 2.0)

prg = check(row(Si=6, Al=3, Mg=4, Ca=2, Na=1), "calcium", "pargasite", 1, 1)
assert math.isclose(float(prg["amp_T_Al"]), 2.0)
assert math.isclose(float(prg["amp_C_Al"]), 1.0)
assert math.isclose(float(prg["amp_A_Na"]), 1.0)

ri = check(row(Si=8, Mg=5, Ca=1, Na=2), "sodium-calcium", "richterite", 1, 0)
gln = check(row(Si=8, Mg=3, Al=2, Na=2), "sodium", "glaucophane/riebeckite", 0, 2)

# Without independently supplied Fe3+, the useful B subgroup remains visible but the root field is withheld.
uncertain = attach_amphibole_ima_diagnostics(
    pd.DataFrame([row(explicit_fe3=False, Si=6, Al=3, Mg=4, Ca=2, Na=1)])
).iloc[0]
assert uncertain["amp_B_subgroup"] == "calcium"
assert "pargasite" in uncertain["amp_root_charge_candidate"]
assert uncertain["amp_root_field"] == ""
assert float(uncertain["amp_Fe3_explicit"]) == 0.0
assert "withheld" in uncertain["amp_classification_note"]

# The public classifier remains deliberately conservative: diagnostics yes, formal species no.
classified = attach_mineral_classification(pd.DataFrame([row(Si=6, Al=3, Mg=4, Ca=2, Na=1)]), "amphibole").iloc[0]
assert classified[SPECIES_COL] == ""
assert "calcium amphibole" in classified[FIELD_COL]
assert "pargasite" in classified[FIELD_COL]
assert "Formal amphibole species is deliberately not assigned" in classified["Комментарий классификации"]

classified_uncertain = attach_mineral_classification(
    pd.DataFrame([row(explicit_fe3=False, Si=6, Al=3, Mg=4, Ca=2, Na=1)]), "amphibole"
).iloc[0]
assert classified_uncertain[SPECIES_COL] == ""
assert "root charge field withheld" in classified_uncertain[FIELD_COL]

# Exercise the real formula-service path. Numeric 1/0 provenance must remain nullable
# so formula validity masking can use NaN without a pandas bool-dtype failure.
oxide = pd.DataFrame([{
    "SiO2": 45.0,
    "Al2O3": 10.0,
    "MgO": 15.0,
    "CaO": 11.0,
    "Na2O": 3.0,
    "K2O": 1.0,
    "FeO": 12.0,
}])
oxide_result = calculate_formula_safe(oxide, "amphibole", "amp_ima2012_23o").data.iloc[0]
assert bool(oxide_result["formula_valid"])
assert float(oxide_result["amp_Fe3_explicit"]) == 0.0
assert oxide_result[SPECIES_COL] == ""
assert "amphibole" in str(oxide_result[FIELD_COL]).lower()

# The old branch had a separate classification page. Recovery keeps the useful A+-C+
# projection as a preset in the existing scientific XY workflow instead of restoring UI clutter.
preset = SCIENTIFIC_PLOT_PRESETS["amphibole_ima2012_a_c"]
assert preset.mineral_key == "amphibole"
assert preset.plot_type == "xy"
assert (preset.x, preset.y) == ("amp_A_plus", "amp_C_plus")
assert preset.overlay_id is None
assert "not" in preset.note.lower() or "не" in preset.note.lower()
assert "10.2138/am.2012.4276" in preset.doi

# Site failures and Li-bearing compositions must never look formally classified.
bad = attach_mineral_classification(pd.DataFrame([row(Si=8, Mg=2, Ca=1)]), "amphibole").iloc[0]
assert bad[SPECIES_COL] == ""
assert "unresolved" in bad[FIELD_COL]

li = attach_amphibole_ima_diagnostics(pd.DataFrame([row(Si=8, Mg=4.9, Li=0.1, Ca=1, Na=1)])).iloc[0]
assert li["amp_site_QC"] != "норма"
assert "Li-bearing" in li["amp_site_QC"]

print("amphibole IMA screening tests: OK")
