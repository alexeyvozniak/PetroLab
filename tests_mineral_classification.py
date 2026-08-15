import math

import pandas as pd

from petrolab.minerals.classification import (
    FIELD_COL,
    LEVEL_COL,
    METHOD_COL,
    NOTE_COL,
    SPECIES_COL,
    attach_garnet_ima_diagnostics,
    attach_mineral_classification,
)
from petrolab.minerals.garnet_ti import apply_strict_grew_figure5
from petrolab.services.formula_service import calculate_formula_safe
from petrolab.ternary_data import prepare_ternary
from petrolab.ternary_overlays import GARNET_TI_GREW_2013_FIG5, attach_ternary_classification
from petrolab.ternary_presets import TERNARY_PRESETS, apply_preset_projection


def near(value, expected, tolerance=1e-8):
    assert math.isfinite(float(value)), value
    assert abs(float(value) - expected) <= tolerance, (value, expected)


# Idealized schorlomite: Ca3 Ti2 (Si Fe3+2) O12.
sch = pd.DataFrame([{"TiO2": 20.0, "apfu_Ca": 3.0, "apfu_Ti": 2.0, "apfu_Si": 1.0, "apfu_Fe3": 2.0}])
sch_d = apply_strict_grew_figure5(attach_garnet_ima_diagnostics(sch)).iloc[0]
near(sch_d["grt_X_sum"], 3.0)
near(sch_d["grt_Y_sum"], 2.0)
near(sch_d["grt_Z_sum"], 3.0)
near(sch_d["TiGrt_Sch"], 100.0)
near(sch_d["TiGrt_Mor"], 0.0)
near(sch_d["TiGrt_Adr"], 0.0)
assert bool(sch_d["TiGrt_Fig5_applicable"])
assert sch_d["TiGrt_field"] == "Schorlomite"
assert sch_d["grt_site_QC"] == "норма"

# Idealized morimotoite: Ca3 Ti Fe2 Si3 O12.
mor = pd.DataFrame([{"TiO2": 20.0, "apfu_Ca": 3.0, "apfu_Ti": 1.0, "apfu_Fe2": 1.0, "apfu_Si": 3.0}])
mor_d = apply_strict_grew_figure5(attach_garnet_ima_diagnostics(mor)).iloc[0]
near(mor_d["TiGrt_Sch"], 0.0)
near(mor_d["TiGrt_Mor"], 100.0)
near(mor_d["TiGrt_Adr"], 0.0)
assert mor_d["TiGrt_field"] == "Morimotoite"

# Grew Fig. 5 explicitly uses Ti + Zr. Hf may be tracked at Y for QC but must not
# move the Schorlomite-Morimotoite-Andradite coordinates.
hf = pd.DataFrame([{
    "TiO2": 20.0,
    "apfu_Ca": 3.0,
    "apfu_Ti": 0.5,
    "apfu_Hf": 0.5,
    "apfu_Fe2": 1.0,
    "apfu_Si": 2.5,
    "apfu_Fe3": 0.5,
}])
hf_d = apply_strict_grew_figure5(attach_garnet_ima_diagnostics(hf)).iloc[0]
near(hf_d["TiGrt_Y_TiZr"], 0.5)
near(hf_d["TiGrt_Y_R4_total_including_Hf"], 1.0)
near(hf_d["TiGrt_Sch"], 100.0)
near(hf_d["TiGrt_Mor"], 0.0)
assert "Hf tracked" in hf_d["grt_site_QC"]

# Grew et al. note possible Mg-dominant analog compositions; flag, never auto-name.
mg_mor = pd.DataFrame([{"TiO2": 20.0, "apfu_Ca": 3.0, "apfu_Ti": 1.0, "apfu_Mg": 1.0, "apfu_Si": 3.0}])
mg_d = apply_strict_grew_figure5(attach_garnet_ima_diagnostics(mg_mor)).iloc[0]
assert bool(mg_d["TiGrt_Mg_morimotoite_analog_flag"])
classified_mg = attach_mineral_classification(mg_mor, "garnet").iloc[0]
assert classified_mg[SPECIES_COL] == ""
assert "Mg-dominant morimotoite-analog" in classified_mg[NOTE_COL]

# Ideal andradite is outside the Ti-rich Figure-5 gate and stays a general end-member field.
adr = pd.DataFrame([{
    "TiO2": 0.0,
    "apfu_Ca": 3.0,
    "apfu_Fe3": 2.0,
    "apfu_Si": 3.0,
    "Adr": 100.0,
    "Prp": 0.0,
    "Alm": 0.0,
    "Sps": 0.0,
    "Grs": 0.0,
    "Uv": 0.0,
}])
adr_c = attach_mineral_classification(adr, "garnet").iloc[0]
assert not bool(adr_c["TiGrt_Fig5_applicable"])
assert adr_c[FIELD_COL] == "Adr-dominant garnet composition"

# Dedicated preset masks analyses outside the published Figure-5 domain.
ti_raw = pd.concat([sch, adr], ignore_index=True, sort=False)
ti_diag = apply_strict_grew_figure5(attach_garnet_ima_diagnostics(ti_raw))
ti_preset = TERNARY_PRESETS["garnet_ti_grew2013"]
projected, components = apply_preset_projection(ti_diag, ti_preset)
assert components == ("TiGrt_Mor", "TiGrt_Adr", "TiGrt_Sch")
assert projected.loc[0, list(components)].notna().all()
assert projected.loc[1, list(components)].isna().all()
prepared = prepare_ternary(projected, *components, normalization="already")
assert len(prepared.valid) == 1
classified_plot = attach_ternary_classification(prepared.valid, ti_preset.field_overlay_id)
assert classified_plot[FIELD_COL].iloc[0] == "Schorlomite field"
assert GARNET_TI_GREW_2013_FIG5.source_doi == "10.2138/am.2013.4201"

# Structural-formula results receive immediate classification where current data suffice.
ol = pd.DataFrame([{"SiO2": 42.73, "MgO": 57.27, "FeO": 0.0}])
ol_r = calculate_formula_safe(ol, "olivine", "ol_4o_fe2").data.iloc[0]
assert ol_r[SPECIES_COL] == "forsterite"
assert "Fo-dominant" in ol_r[FIELD_COL]
assert ol_r[LEVEL_COL] == "composition-based"

# Explicit zeros mean measured/defined zero; an absent feldspar endmember oxide is not
# interchangeable with zero under the formula input contract.
fsp = pd.DataFrame([{
    "SiO2": 68.74,
    "Al2O3": 19.44,
    "Na2O": 11.82,
    "K2O": 0.0,
    "CaO": 0.0,
}])
fsp_r = calculate_formula_safe(fsp, "feldspar", "fsp_8o").data.iloc[0]
assert bool(fsp_r["formula_valid"])
assert fsp_r[SPECIES_COL] == "albite"
assert fsp_r[FIELD_COL] == "Albite"
assert "Gündüz" in fsp_r[METHOD_COL]

# Amphibole now exposes conservative IMA site/subgroup diagnostics, but routine
# EPMA without independently supplied Fe3+ or W-site H/O must still refuse a
# formal species name.
amp = pd.DataFrame([{
    "SiO2": 45.0,
    "Al2O3": 10.0,
    "MgO": 15.0,
    "CaO": 11.0,
    "Na2O": 3.0,
    "K2O": 1.0,
    "FeO": 12.0,
}])
amp_r = calculate_formula_safe(amp, "amphibole", "amp_ima2012_23o").data.iloc[0]
assert bool(amp_r["formula_valid"])
assert amp_r[SPECIES_COL] == ""
assert "amphibole" in amp_r[FIELD_COL]
assert "IMA 2012" in amp_r[LEVEL_COL]
assert float(amp_r["amp_Fe3_explicit"]) == 0.0
assert "Formal amphibole species is deliberately not assigned" in amp_r[NOTE_COL]
assert "W site unresolved" in amp_r[NOTE_COL]
assert "Hawthorne" in amp_r[METHOD_COL]
assert "Locock" in amp_r[METHOD_COL]

# Apatite reports useful X-anion dominance without pretending the full subgroup is known.
apt = pd.DataFrame([{"P2O5": 42.0, "CaO": 55.0, "F": 3.0, "Cl": 0.0}])
apt_r = calculate_formula_safe(apt, "apatite", "ap_ketcham25").data.iloc[0]
assert apt_r[SPECIES_COL] == ""
assert "fluorapatite" in apt_r[FIELD_COL]
assert "X-anion" in apt_r[LEVEL_COL]

print("mineral classification tests: OK")
