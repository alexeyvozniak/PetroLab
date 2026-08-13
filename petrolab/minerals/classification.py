from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from petrolab.ternary_data import prepare_ternary
from petrolab.ternary_overlays import (
    attach_ternary_classification,
    classify_feldspar_gunduz_asan,
)
from petrolab.ternary_presets import TERNARY_PRESETS, apply_preset_projection


SPECIES_COL = "Минеральный вид (авто)"
FIELD_COL = "Классификационное поле"
LEVEL_COL = "Уровень классификации"
METHOD_COL = "Метод классификации"
NOTE_COL = "Комментарий классификации"

CLASSIFICATION_COLUMNS = (SPECIES_COL, FIELD_COL, LEVEL_COL, METHOD_COL, NOTE_COL)


@dataclass(frozen=True)
class ClassificationDecision:
    species: str = ""
    field: str = ""
    level: str = ""
    method: str = ""
    note: str = ""


_GARNET_SITE_SEQUENCE_SOURCE = (
    "Grew et al. (2013), American Mineralogist 98, 785–811, "
    "doi:10.2138/am.2013.4201"
)


def _apfu_value(row: pd.Series, element: str) -> float:
    value = row.get(f"apfu_{element}", 0.0)
    try:
        result = float(value)
    except (TypeError, ValueError):
        return 0.0
    return result if np.isfinite(result) and result > 0 else 0.0


def _put(site: dict[str, float], element: str, amount: float) -> None:
    if amount <= 0:
        return
    site[element] = site.get(element, 0.0) + float(amount)


def _fill_to_capacity(source: dict[str, float], element: str, site: dict[str, float], capacity: float) -> None:
    available = source.get(element, 0.0)
    room = max(float(capacity) - sum(site.values()), 0.0)
    moved = min(available, room)
    _put(site, element, moved)
    source[element] = max(available - moved, 0.0)


def _allocate_one_garnet(row: pd.Series) -> dict[str, float | str | bool]:
    elements = (
        "Li", "Zn", "P", "V5", "Si", "Al", "Fe3", "Ca", "Na", "K", "Y",
        "La", "Ce", "Nd", "Th", "Pb", "Ti", "V3", "Cr", "Mn3", "Ga", "Zr",
        "Hf", "Nb", "Sn", "Sb", "Te6", "U", "Mg", "Fe2", "Mn", "Sr", "Ba",
    )
    remaining = {element: _apfu_value(row, element) for element in elements}
    x: dict[str, float] = {}; y: dict[str, float] = {}; z: dict[str, float] = {}
    for element in ("Li", "Zn", "P", "V5"): _fill_to_capacity(remaining, element, z, 3.0)
    for element in ("Si", "Al", "Fe3"): _fill_to_capacity(remaining, element, z, 3.0)
    for element in ("Ca", "Na", "K", "Y", "La", "Ce", "Nd", "Th", "Pb", "Sr", "Ba"):
        _put(x, element, remaining.get(element, 0.0)); remaining[element] = 0.0
    for element in ("Al", "Ti", "V3", "Cr", "Mn3", "Fe3", "Ga", "Zr", "Hf", "Nb", "Sn", "Sb", "Te6", "U"):
        _put(y, element, remaining.get(element, 0.0)); remaining[element] = 0.0
    _fill_to_capacity(remaining, "Fe2", z, 3.0)
    if sum(y.values()) > 2.0 and sum(z.values()) < 3.0 and y.get("Ti", 0.0) > 0:
        transfer = min(y["Ti"], 3.0 - sum(z.values()), sum(y.values()) - 2.0)
        y["Ti"] -= transfer; _put(z, "Ti", transfer)
    for element in ("Mg", "Fe2", "Mn"):
        _fill_to_capacity(remaining, element, y, 2.0); _put(x, element, remaining.get(element, 0.0)); remaining[element] = 0.0
    x_sum = sum(x.values()); y_sum = sum(y.values()); z_sum = sum(z.values())
    y_r4 = sum(y.get(element, 0.0) for element in ("Ti", "Zr", "Hf"))
    z_r3 = sum(z.get(element, 0.0) for element in ("Al", "Fe3"))
    y_r3 = sum(y.get(element, 0.0) for element in ("Al", "Fe3", "Cr", "V3", "Mn3"))
    y_r2 = sum(y.get(element, 0.0) for element in ("Mg", "Fe2", "Mn"))
    sch_raw = min(y_r4, z_r3); mor_raw = max(y_r4 - sch_raw, 0.0); adr_raw = y_r3
    component_total = sch_raw + mor_raw + adr_raw
    if component_total > 0:
        sch = 100.0 * sch_raw / component_total; mor = 100.0 * mor_raw / component_total; adr = 100.0 * adr_raw / component_total
    else: sch = mor = adr = np.nan
    try: ti_wt = float(row.get("TiO2", np.nan))
    except (TypeError, ValueError): ti_wt = np.nan
    ti_apfu = _apfu_value(row, "Ti"); zr_apfu = _apfu_value(row, "Zr")
    fig5_applicable = bool(np.isfinite(ti_wt) and ti_wt > 12.0 and ti_apfu > zr_apfu)
    qc_ok = abs(x_sum - 3.0) <= 0.20 and abs(y_sum - 2.0) <= 0.20 and abs(z_sum - 3.0) <= 0.20
    qc_messages: list[str] = []
    if not qc_ok: qc_messages.append("site sums deviate from X=3, Y=2, Z=3")
    if sum(remaining.values()) > 0.05: qc_messages.append("unallocated cations remain")
    if y.get("Hf", 0.0) > 0.05: qc_messages.append("Hf materially contributes to the R4+ proxy")
    if x.get("Sr", 0.0) + x.get("Ba", 0.0) > 0.05: qc_messages.append("Sr/Ba-rich X site: simplified end-member proxy only")
    dominant = ""
    if all(np.isfinite(value) for value in (sch, mor, adr)):
        values = {"Schorlomite": sch, "Morimotoite": mor, "Andradite": adr}; dominant = max(values, key=values.get)
    mg_mor_candidate = bool(fig5_applicable and dominant == "Morimotoite" and y.get("Mg", 0.0) > y.get("Fe2", 0.0))
    output: dict[str, float | str | bool] = {
        "grt_X_sum": x_sum, "grt_Y_sum": y_sum, "grt_Z_sum": z_sum,
        "grt_site_QC": "норма" if not qc_messages else "; ".join(qc_messages),
        "TiGrt_Sch": sch, "TiGrt_Mor": mor, "TiGrt_Adr": adr,
        "TiGrt_Fig5_applicable": fig5_applicable, "TiGrt_field": dominant,
        "TiGrt_Mg_morimotoite_analog_flag": mg_mor_candidate,
        "TiGrt_Y_R4": y_r4, "TiGrt_Z_R3": z_r3, "TiGrt_Y_R3": y_r3, "TiGrt_Y_R2": y_r2,
    }
    for site_name, site in (("X", x), ("Y", y), ("Z", z)):
        for element, value in site.items(): output[f"grt_{site_name}_{element}"] = value
    return output


def attach_garnet_ima_diagnostics(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()
    if result.empty: return result
    diagnostics = pd.DataFrame([_allocate_one_garnet(row) for _, row in result.iterrows()], index=result.index)
    for column in diagnostics.columns: result[column] = diagnostics[column]
    return result


def _empty_decisions(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()
    for column in CLASSIFICATION_COLUMNS: result[column] = ""
    return result


def _set_decision(result: pd.DataFrame, index, decision: ClassificationDecision) -> None:
    result.at[index, SPECIES_COL] = decision.species; result.at[index, FIELD_COL] = decision.field
    result.at[index, LEVEL_COL] = decision.level; result.at[index, METHOD_COL] = decision.method; result.at[index, NOTE_COL] = decision.note


def _classify_pyroxene(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = _empty_decisions(dataframe); preset = TERNARY_PRESETS["pyroxene_wo_en_fs"]
    projected, components = apply_preset_projection(dataframe, preset); prepared = prepare_ternary(projected, *components, normalization="already")
    if not prepared.valid.empty:
        classified = attach_ternary_classification(prepared.valid, preset.field_overlay_id)
        for index, row in classified.iterrows():
            _set_decision(result, index, ClassificationDecision(field=str(row.get(FIELD_COL, "")), level="IMA/Morimoto compositional classification", method="Morimoto et al. (1988) after Q–J gating", note="Wo–En–Fs classification is applied only to Quad pyroxenes."))
    return result


def _classify_feldspar(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = _empty_decisions(dataframe)
    if not {"Ab", "An", "Or"}.issubset(dataframe.columns): return result
    prepared = prepare_ternary(dataframe, "Ab", "An", "Or", normalization="auto")
    for index, row in prepared.valid.iterrows():
        field = classify_feldspar_gunduz_asan(row); species = field.lower() if field in {"Albite", "Anorthite"} else ""
        _set_decision(result, index, ClassificationDecision(species=species, field=field, level="Ab–An–Or compositional classification", method="Gündüz & Asan (2023)", note="Sanidine, orthoclase and microcline are not assigned from chemistry alone."))
    return result


def _classify_garnet(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = _empty_decisions(attach_garnet_ima_diagnostics(dataframe)); common = [c for c in ("Prp", "Alm", "Sps", "Grs", "Adr", "Uv") if c in result]
    for index, row in result.iterrows():
        if bool(row.get("TiGrt_Fig5_applicable", False)) and row.get("TiGrt_field"):
            note = "Grew et al. (2013), Fig. 5 is a Ti-rich garnet diagnostic, not a formal species assignment."
            if bool(row.get("TiGrt_Mg_morimotoite_analog_flag", False)): note += " Mg-dominant morimotoite-analog composition possible."
            _set_decision(result, index, ClassificationDecision(field=f"{row['TiGrt_field']} field · Ti-rich garnet diagnostic", level="Ti-garnet compositional diagnostic", method=_GARNET_SITE_SEQUENCE_SOURCE + "; Fig. 5", note=note)); continue
        values = {}
        for column in common:
            try: value = float(row.get(column, np.nan))
            except (TypeError, ValueError): continue
            if np.isfinite(value): values[column] = value
        if values:
            dominant = max(values, key=values.get); _set_decision(result, index, ClassificationDecision(field=f"{dominant}-dominant garnet composition", level="dominant end-member composition", method=_GARNET_SITE_SEQUENCE_SOURCE, note="Formal IMA species assignment requires complete site/valence/anion treatment."))
    return result


def _classify_olivine(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = _empty_decisions(dataframe); components = {"Fo": "forsterite", "Fa": "fayalite", "Te": "tephroite"}
    for index, row in result.iterrows():
        values = {}
        for column in components:
            try: value = float(row.get(column, np.nan))
            except (TypeError, ValueError): continue
            if np.isfinite(value): values[column] = value
        if not values: continue
        dominant = max(values, key=values.get); ca_ol = float(row.get("Ca-ol", 0.0) or 0.0); species = components[dominant] if values[dominant] > 50.0 and ca_ol < 10.0 else ""
        _set_decision(result, index, ClassificationDecision(species=species, field=f"{dominant}-dominant olivine composition", level="composition-based" if species else "compositional field", method="Fo–Fa–Te–Ca-ol end-member proportions", note="Ca-rich olivines are not named automatically."))
    return result


def _classify_apatite(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = _empty_decisions(dataframe)
    for index, row in result.iterrows():
        basis = str(row.get("OH_est_basis", ""))
        if basis != "F и Cl измерены":
            _set_decision(result, index, ClassificationDecision(field="Apatite X-anion field unresolved", level="insufficient X-anion data", method="Pasero et al. (2010)", note="F and Cl must both be measured before OH can be inferred from site balance and X-anion dominance assessed.")); continue
        candidates = {"F": row.get("apfu_F", np.nan), "Cl": row.get("apfu_Cl", np.nan), "OH": row.get("apfu_OH_est", np.nan)}; finite = {}
        for name, value in candidates.items():
            try: number = float(value)
            except (TypeError, ValueError): continue
            if np.isfinite(number) and number >= 0: finite[name] = number
        if not finite: continue
        dominant = max(finite, key=finite.get); field_name = {"F": "fluorapatite", "Cl": "chlorapatite", "OH": "hydroxylapatite"}[dominant]
        _set_decision(result, index, ClassificationDecision(field=f"{field_name} X-anion field", level="apatite X-anion compositional field", method="Pasero et al. (2010) apatite-supergroup anion dominance", note="Formal species name is withheld until the cation/tetrahedral subgroup is verified."))
    return result


def _classify_amphibole(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = _empty_decisions(dataframe)
    for index in result.index: _set_decision(result, index, ClassificationDecision(field="Amphibole · formal species not yet assigned", level="insufficient for formal IMA species", method="Hawthorne et al. (2012); Locock (2014)", note="Complete A/B/C/T/W site allocation and redox/W-anion treatment are not yet implemented."))
    return result


def _generic_status(dataframe: pd.DataFrame, mineral_key: str) -> pd.DataFrame:
    result = _empty_decisions(dataframe)
    for index in result.index: _set_decision(result, index, ClassificationDecision(field=f"{mineral_key}: automatic species classifier not yet validated", level="classifier unavailable", note="Structural formula results remain available and can be used in diagrams."))
    return result


def attach_mineral_classification(dataframe: pd.DataFrame, mineral_key: str, method_id: str | None = None) -> pd.DataFrame:
    key = str(mineral_key)
    if key in {"clinopyroxene", "orthopyroxene", "cpx", "opx"}: return _classify_pyroxene(dataframe)
    if key == "feldspar": return _classify_feldspar(dataframe)
    if key == "garnet": return _classify_garnet(dataframe)
    if key == "olivine": return _classify_olivine(dataframe)
    if key == "apatite": return _classify_apatite(dataframe)
    if key == "amphibole": return _classify_amphibole(dataframe)
    return _generic_status(dataframe, key)
