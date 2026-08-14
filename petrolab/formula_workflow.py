"""Conservative defaults for the import → formula workflow.

The recommendation only preselects a documented method in the UI. It never
saves a derived result, so the researcher still sees and confirms the chosen
normalisation and assumptions.
"""
from __future__ import annotations

from petrolab.minerals.formulae import FormulaMethod, methods_for


RECOMMENDED_METHODS = {
    "olivine": "ol_droop_4o",
    "clinopyroxene": "px_morimoto_droop",
    "orthopyroxene": "px_morimoto_droop",
    "garnet": "grt_grew_droop",
    "feldspar": "fsp_8o",
    "mica": "mica_rieder_11o",
    "amphibole": "amp_ima2012_23o",
    "spinel": "sp_droop_4o",
    "fe_ti_oxide": "ilm_droop_3o",
    "apatite": "ap_ketcham25",
    "perovskite": "pv_3o",
    "nepheline": "ne_henderson32",
    "carbonate": "carb_1cat",
    "titanite": "ttn_minplot",
    "zircon": "zrn_4o",
}


def recommended_method(mineral_key: str) -> FormulaMethod | None:
    methods = methods_for(mineral_key)
    if not methods:
        return None
    wanted = RECOMMENDED_METHODS.get(mineral_key)
    return next((method for method in methods if method.id == wanted), methods[0])
