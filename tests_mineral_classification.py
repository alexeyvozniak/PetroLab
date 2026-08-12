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
from petrolab.services.formula_service import calculate_formula_safe
from petrolab.ternary_data import prepare_ternary
from petrolab.ternary_overlays import (
    GARNET_TI_GREW_2013_FIG5,
    attach_ternary_classification,
)
from petrolab.ternary_presets import TERNARY_PRESETS, apply_preset_projection


def near(value, expected, tolerance=1e-8):
    assert math.isfinite(float(value)), value
    assert abs(float(value) - expected) <= tolerance, (value, expected)


# --- Grew et al. (2013) garnet site allocation and Figure-5 component logic ---
# Idealized schorlomite: Ca3 Ti2 (Si Fe3+2) O12.
sch = pd.DataFrame(
    [{
        "TiO2": 20.0,
        "apfu_Ca": 3.0,
        "apfu_Ti": 2.0,
        "apfu_Si": 1.0,
        "apfu_Fe3": 2.0,
    }]
)
sch_d = attach_garnet_ima_diagnostics(sch).iloc[0]
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
mor = pd.DataFrame(
    [{
        "TiO2": 20.0,
        "apfu_Ca": 3.0,
        "apfu_Ti": 1.0,
        "apfu_Fe2": 1.0,
        "apfu_Si": 3.0,
    }]
)
mor_d = attach_garnet_ima_diagnostics(mor).iloc[0]
near(mor_d["TiGrt_Sch"], 0.0)
near(mor_d["TiGrt_Mor"], 100.0)
near(mor_d["TiGrt_Adr"], 0.0)
assert mor_d["TiGrt_field"] == "Morimotoite"

# Grew et al. note possible Mg-dominant analog compositions; they must be flagged,
# never promoted silently to an approved mineral species.
mg_mor = pd.DataFrame(
    [{
        "TiO2": 20.0,
        "apfu_Ca": 3.0,
        "apfu_Ti": 1.0,
        "apfu_Mg": 1.0,
        "apfu_Si": 3.0,
    }]
)
mg_d = attach_garnet_ima_diagnostics(mg_mor).iloc[0]
assert bool(mg_d["TiGrt_Mg_morimotoite_analog_flag"])
classified_mg = attach_mineral_classification(mg_mor, "garnet").iloc[0]
assert classified_mg[SPECIES_COL] == ""
assert "Mg-dominant morimotoite-analog" in classified_mg[NOTE_COL]

# Ideal andradite is handled by the general end-member layer when the Fig. 5 Ti gate
# is not applicable; it must not be forced into the Ti-rich diagnostic plot.
adr = pd.DataFrame(
    [{
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
    }]
)
adr_c = attach_mineral_classification(adr, "garnet").iloc[0]
assert not bool(adr_c["TiGrt_Fig5_applicable"])
assert adr_c[FIELD_COL] == "Adr-dominant garnet composition"

# The dedicated ternary preset masks rows outside the published Figure-5 domain.
ti_raw = pd.concat([sch, adr], ignore_index=True, sort=False)
ti_diag = attach_garnet_ima_diagnostics(ti_raw)
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

# --- Classification is attached automatically to structural-formula results ---
# Ideal forsterite should receive an immediate composition-based species name.
ol = pd.DataFrame([{"SiO2": 42.73, "MgO": 57.27, "FeO": 0.0}])
ol_r = calculate_formula_safe(ol, "olivine", "ol_4o_fe2").data.iloc[0]
assert ol_r[SPECIES_COL] == "forsterite"
assert "Fo-dominant" in ol_r[FIELD_COL]
assert ol_r[LEVEL_COL] == "composition-based"

# Albite end of Ab-An-Or can be named; K-feldspar structural species remain unresolved.
fsp = pd.DataFrame([{"SiO2": 68.74, "Al2O3": 19.44, "Na2O": 11.82}])
fsp_r = calculate_formula_safe(fsp, "feldspar", "fsp_8o").data.iloc[0]
assert fsp_r[SPECIES_COL] == "albite"
assert fsp_r[FIELD_COL] == "Albite"
assert "Gündüz" in fsp_r[METHOD_COL]

# Current amphibole recast must explicitly refuse a guessed IMA species.
amp = pd.DataFrame(
    [{
        "SiO2": 45.0,
        "Al2O3": 10.0,
        "MgO": 15.0,
        "CaO": 11.0,
        "Na2O": 3.0,
        "K2O": 1.0,
        "FeO": 12.0,
    }]
)
amp_r = calculate_formula_safe(amp, "amphibole", "amp_ima2012_23o").data.iloc[0]
assert amp_r[SPECIES_COL] == ""
assert "formal species not yet assigned" in amp_r[FIELD_COL]
assert amp_r[LEVEL_COL] == "insufficient for formal IMA species"
assert "A/B/C/T/W" in amp_r[NOTE_COL]
assert "Hawthorne" in amp_r[METHOD_COL]

# Apatite gives an immediately useful X-anion field but not a false full-supergroup name.
apt = pd.DataFrame(
    [{
        "P2O5": 42.0,
        "CaO": 55.0,
        "F": 3.0,
        "Cl": 0.0,
    }]
)
apt_r = calculate_formula_safe(apt, "apatite", "ap_ketcham25").data.iloc[0]
assert apt_r[SPECIES_COL] == ""
assert "fluorapatite" in apt_r[FIELD_COL]
assert "X-anion" in apt_r[LEVEL_COL]

print("mineral classification tests: OK")
