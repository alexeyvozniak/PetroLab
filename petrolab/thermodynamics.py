"""Versioned thermodynamic calculations attached to immutable analysis IDs.

This module complements the legacy Cpx-only ``petrolab.thermobarometry`` workflow.
It deliberately supports only single-mineral and mineral–melt methods: no two-mineral
pairing is performed here.  Every registered method carries its primary citation,
calibration note and uncertainty, and saved results never overwrite source chemistry.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Callable

import numpy as np
import pandas as pd

from petrolab.analysis_identity import source_row_fingerprint
from petrolab.db import _json_safe_record, _utcnow, connect
from petrolab.minerals.formulae import OXIDES, oxygen_normalized_apfu
from petrolab.thermobarometry import (
    QC_FAIL,
    QC_INSUFFICIENT_INPUT,
    QC_PASS,
    QC_WARNING,
    calculate_putirka_2008_cpx_only_t32d,
)


MODE_SINGLE_MINERAL = "single_mineral"
MODE_MINERAL_MELT = "mineral_melt"
KIND_TEMPERATURE = "temperature"
KIND_PRESSURE = "pressure"
KIND_FUGACITY = "fugacity"


@dataclass(frozen=True)
class ThermodynamicMethod:
    method_id: str
    title: str
    short_title: str
    input_mode: str
    parameter_kind: str
    mineral_key: str
    source_citation: str
    source_doi: str
    equation_version: str
    uncertainty: str
    calibration_range: str
    required_mineral_components: tuple[str, ...]
    required_melt_components: tuple[str, ...] = ()
    output_columns: tuple[str, ...] = ()
    assumptions: str = ""

    def validate(self) -> None:
        if self.input_mode not in {MODE_SINGLE_MINERAL, MODE_MINERAL_MELT}:
            raise ValueError(f"Недопустимый input_mode: {self.input_mode}")
        if self.parameter_kind not in {KIND_TEMPERATURE, KIND_PRESSURE, KIND_FUGACITY}:
            raise ValueError(f"Недопустимый parameter_kind: {self.parameter_kind}")
        required = {
            "method_id": self.method_id,
            "title": self.title,
            "short_title": self.short_title,
            "mineral_key": self.mineral_key,
            "source_citation": self.source_citation,
            "source_doi": self.source_doi,
            "equation_version": self.equation_version,
            "uncertainty": self.uncertainty,
            "calibration_range": self.calibration_range,
        }
        missing = [key for key, value in required.items() if not str(value).strip()]
        if missing:
            raise ValueError("Неполный scientific contract: " + ", ".join(missing))
        doi = self.source_doi.strip().lower()
        if not doi.startswith("10.") or "/" not in doi:
            raise ValueError("source_doi должен быть DOI первичной публикации")


PUTIRKA_2008_CPX_ONLY = ThermodynamicMethod(
    method_id="putirka_2008_cpx_only_t32d",
    title="Putirka (2008) · Cpx-only thermometer · Eq. 32d",
    short_title="Cpx-only T · Putirka 2008 Eq. 32d",
    input_mode=MODE_SINGLE_MINERAL,
    parameter_kind=KIND_TEMPERATURE,
    mineral_key="clinopyroxene",
    source_citation="Putirka, K.D. (2008). Thermometers and Barometers for Volcanic Systems. Reviews in Mineralogy and Geochemistry 69, 61–120.",
    source_doi="10.2138/rmg.2008.69.3",
    equation_version="Published Eq. 32d; PetroLab legacy implementation 1.0.0",
    uncertainty="SEE ±58 °C for anhydrous data; ±87 °C reported for hydrous data.",
    calibration_range="Anhydrous clinopyroxene thermometer. Pressure is an independently supplied assumption.",
    required_mineral_components=("SiO2", "TiO2", "Al2O3", "Cr2O3", "FeOt", "MgO", "CaO", "Na2O", "K2O"),
    output_columns=("T (°C)", "T (K)", "P assumption (kbar)"),
    assumptions="Does not independently solve P–T and is not a mineral–melt equilibrium test.",
)

PUTIRKA_2016_AMP_EQ5 = ThermodynamicMethod(
    method_id="putirka_2016_amp_only_eq5",
    title="Putirka (2016) · Amphibole-only thermometer · Eq. 5",
    short_title="Amp-only T · Putirka 2016 Eq. 5",
    input_mode=MODE_SINGLE_MINERAL,
    parameter_kind=KIND_TEMPERATURE,
    mineral_key="amphibole",
    source_citation="Putirka, K.D. (2016). Amphibole thermometers and barometers for igneous systems. American Mineralogist 101, 841–858.",
    source_doi="10.2138/am-2016-5506",
    equation_version="Published Eq. 5; PetroLab implementation 1.0.0",
    uncertainty="Use within the calibration/application limits discussed by Putirka (2016); PetroLab reports the equation result without adding an invented precision.",
    calibration_range="Calcic igneous amphiboles; composition- and temperature-sensitive. Textural and petrologic applicability must be assessed by the user.",
    required_mineral_components=("SiO2", "TiO2", "Al2O3", "FeOt", "MgO", "CaO", "Na2O", "K2O"),
    output_columns=("T (°C)", "T (K)"),
)

MUTCH_2016_AMP_BAROMETER = ThermodynamicMethod(
    method_id="mutch_2016_amp_al_barometer",
    title="Mutch et al. (2016) · revised Al-in-hornblende barometer · Eq. 5",
    short_title="Amp-only P · Mutch 2016",
    input_mode=MODE_SINGLE_MINERAL,
    parameter_kind=KIND_PRESSURE,
    mineral_key="amphibole",
    source_citation="Mutch, E.J.F. et al. (2016). An experimental study of amphibole stability in low-pressure granitic magmas and a revised Al-in-hornblende geobarometer. Contributions to Mineralogy and Petrology 171, 85.",
    source_doi="10.1007/s00410-016-1298-9",
    equation_version="Published Eq. 5; PetroLab implementation 1.0.0",
    uncertainty="±16 % relative uncertainty for the calibrant dataset.",
    calibration_range="Granitic low-variance assemblage; amphibole rims in textural equilibrium near the haplogranite solidus. Not a generic pressure equation for arbitrary amphibole.",
    required_mineral_components=("SiO2", "TiO2", "Al2O3", "FeOt", "MgO", "CaO", "Na2O", "K2O"),
    output_columns=("P (kbar)", "Al total (apfu, 23 O)"),
    assumptions="Requires the assemblage and rim-texture criteria of Mutch et al. (2016).",
)

FERRY_WATSON_2007_TI_ZIRCON = ThermodynamicMethod(
    method_id="ferry_watson_2007_ti_zircon",
    title="Ferry & Watson (2007) · Ti-in-zircon thermometer",
    short_title="Zircon T · Ferry & Watson 2007",
    input_mode=MODE_SINGLE_MINERAL,
    parameter_kind=KIND_TEMPERATURE,
    mineral_key="zircon",
    source_citation="Ferry, J.M. & Watson, E.B. (2007). New thermodynamic models and revised calibrations for the Ti-in-zircon and Zr-in-rutile thermometers. Contributions to Mineralogy and Petrology 154, 429–437.",
    source_doi="10.1007/s00410-007-0201-0",
    equation_version="Published activity-corrected calibration; PetroLab implementation 1.0.0",
    uncertainty="Calibration coefficients: intercept 5.711 ±0.072 and 4800 ±86 K.",
    calibration_range="Ti-in-zircon calibration; aSiO2 and aTiO2 must be supplied explicitly when not buffered at unity.",
    required_mineral_components=("Ti [µg/g]",),
    output_columns=("T (°C)", "T (K)", "aSiO2", "aTiO2"),
)

LOUCKS_2020_ZIRCON_DFMQ = ThermodynamicMethod(
    method_id="loucks_2020_zircon_dfmq",
    title="Loucks et al. (2020) · zircon Ce–U–Ti oxybarometer",
    short_title="Zircon ΔFMQ · Loucks 2020",
    input_mode=MODE_SINGLE_MINERAL,
    parameter_kind=KIND_FUGACITY,
    mineral_key="zircon",
    source_citation="Loucks, R.R., Fiorentini, M.L. & Henríquez, G.J. (2020). New Magmatic Oxybarometer Using Trace Elements in Zircon. Journal of Petrology 61, egaa034.",
    source_doi="10.1093/petrology/egaa034",
    equation_version="Empirical calibration Eq. 7b; PetroLab implementation 1.0.0",
    uncertainty="Standard error ±0.6 log unit fO2.",
    calibration_range="Calibrated from FMQ −4.9 to FMQ +2.9 for broad mafic-to-felsic magmatic suites. Ui is age-corrected initial U.",
    required_mineral_components=("Ce [µg/g]", "Ui [µg/g]", "Ti [µg/g]"),
    output_columns=("ΔFMQ", "Ce (µg/g)", "Ui (µg/g)", "Ti (µg/g)"),
    assumptions="Measured U is never silently treated as age-corrected Ui; that substitution requires explicit user confirmation.",
)

PUTIRKA_2008_OL_LIQ_EQ22 = ThermodynamicMethod(
    method_id="putirka_2008_ol_liq_eq22",
    title="Putirka (2008) · olivine–liquid thermometer · Eq. 22",
    short_title="Ol–melt T · Putirka 2008 Eq. 22",
    input_mode=MODE_MINERAL_MELT,
    parameter_kind=KIND_TEMPERATURE,
    mineral_key="olivine",
    source_citation="Putirka, K.D. (2008). Thermometers and Barometers for Volcanic Systems. Reviews in Mineralogy and Geochemistry 69, 61–120.",
    source_doi="10.2138/rmg.2008.69.3",
    equation_version="Published Eq. 22 (after Putirka et al. 2007 Eq. 4); PetroLab implementation 1.0.0",
    uncertainty="SEE ±45 °C for anhydrous and ±29 °C for hydrous data as summarized for Eq. 22.",
    calibration_range="Olivine–liquid thermometer. PetroLab pairs the selected olivines with one explicitly supplied representative melt composition; no automatic melt matching is performed.",
    required_mineral_components=("MgO",),
    required_melt_components=("SiO2", "TiO2", "Al2O3", "FeOt", "MnO", "MgO", "CaO", "Na2O", "K2O", "H2O"),
    output_columns=("T (°C)", "T (K)", "P assumption (kbar)", "DMg ol/melt"),
    assumptions="The selected mineral and melt must be cogenetic/equilibrated; PetroLab does not infer that relation from composition alone.",
)

METHODS = (
    PUTIRKA_2008_CPX_ONLY,
    PUTIRKA_2016_AMP_EQ5,
    MUTCH_2016_AMP_BAROMETER,
    FERRY_WATSON_2007_TI_ZIRCON,
    LOUCKS_2020_ZIRCON_DFMQ,
    PUTIRKA_2008_OL_LIQ_EQ22,
)
for _method in METHODS:
    _method.validate()
if len({method.method_id for method in METHODS}) != len(METHODS):
    raise ValueError("Повторный thermodynamic method_id")


def method_by_id(method_id: str) -> ThermodynamicMethod:
    for method in METHODS:
        if method.method_id == str(method_id):
            return method
    raise ValueError("Термодинамическая калибровка не зарегистрирована")


def methods_for_mineral(mineral_key: str, *, input_mode: str | None = None) -> tuple[ThermodynamicMethod, ...]:
    return tuple(
        method for method in METHODS
        if method.mineral_key == str(mineral_key)
        and (input_mode is None or method.input_mode == input_mode)
    )


def _blank_result(index: pd.Index) -> pd.DataFrame:
    return pd.DataFrame({
        "Thermodynamic status": QC_INSUFFICIENT_INPUT,
        "Thermodynamic reason": "",
    }, index=index)


def _require_finite_nonnegative(dataframe: pd.DataFrame, columns: tuple[str, ...]) -> tuple[pd.Series, dict[object, str]]:
    ok = pd.Series(True, index=dataframe.index, dtype=bool)
    reasons: dict[object, str] = {}
    for column in columns:
        if column not in dataframe.columns:
            ok[:] = False
            for idx in dataframe.index:
                reasons[idx] = (reasons.get(idx, "") + f"; нет {column}").strip("; ")
            continue
        values = pd.to_numeric(dataframe[column], errors="coerce")
        bad = values.isna() | ~np.isfinite(values.to_numpy(dtype=float)) | values.lt(0)
        ok &= ~bad
        for idx in dataframe.index[bad]:
            reasons[idx] = (reasons.get(idx, "") + f"; невалидный {column}").strip("; ")
    return ok, reasons


def _trace_candidates(element: str, *, initial_u: bool = False) -> tuple[str, ...]:
    if initial_u:
        return (
            "Ui [µg/g]", "U_i [µg/g]", "Ui [μg/g]", "U_i [μg/g]",
            "Ui [ppm]", "U_i [ppm]", "Ui", "U_i",
        )
    return (
        f"{element} [µg/g]", f"{element} [μg/g]", f"{element} [ppm]",
        f"{element}_ppm", f"{element} ppm", element,
    )


def _trace_series(dataframe: pd.DataFrame, element: str, *, initial_u: bool = False) -> tuple[pd.Series, str | None]:
    candidates = [name for name in _trace_candidates(element, initial_u=initial_u) if name in dataframe.columns]
    if not candidates:
        return pd.Series(np.nan, index=dataframe.index, dtype=float), None
    populated = []
    for name in candidates:
        values = pd.to_numeric(dataframe[name], errors="coerce")
        if values.notna().any():
            populated.append((name, values))
    if not populated:
        return pd.Series(np.nan, index=dataframe.index, dtype=float), candidates[0]
    if len(populated) > 1:
        reference = populated[0][1]
        for _, values in populated[1:]:
            same = (reference.fillna(-9.87654321e307) == values.fillna(-9.87654321e307)).all()
            if not bool(same):
                raise ValueError(
                    f"Несколько неоднозначных колонок {element}: " + ", ".join(name for name, _ in populated)
                )
    return populated[0][1], populated[0][0]


def calculate_putirka_2016_amp_eq5(dataframe: pd.DataFrame, *, applicability_confirmed: bool) -> pd.DataFrame:
    result = _blank_result(dataframe.index)
    try:
        apfu, _, _ = oxygen_normalized_apfu(dataframe, 23.0)
    except ValueError as exc:
        result["Thermodynamic reason"] = str(exc)
        return result
    needed = ("Si", "Ti", "Fe2", "Na")
    if any(column not in apfu.columns for column in needed):
        result["Thermodynamic reason"] = "Недостаточно компонентов для 23-O amphibole formula"
        return result
    fet = apfu.get("Fe2", 0.0) + apfu.get("Fe3", 0.0)
    t_c = 1781.0 - 132.74 * apfu["Si"] + 116.6 * apfu["Ti"] - 69.41 * fet + 101.62 * apfu["Na"]
    good = np.isfinite(t_c.to_numpy(dtype=float))
    result["T (°C)"] = np.where(good, t_c, np.nan)
    result["T (K)"] = np.where(good, t_c + 273.15, np.nan)
    result.loc[good, "Thermodynamic status"] = QC_PASS if applicability_confirmed else QC_WARNING
    result.loc[good, "Thermodynamic reason"] = (
        "Eq. 5 рассчитано на 23 O. Применимость подтверждена."
        if applicability_confirmed
        else "Eq. 5 рассчитано, но текстурная/петрологическая применимость не подтверждена."
    )
    return result


def calculate_mutch_2016_amp_barometer(dataframe: pd.DataFrame, *, assemblage_confirmed: bool) -> pd.DataFrame:
    result = _blank_result(dataframe.index)
    try:
        apfu, _, _ = oxygen_normalized_apfu(dataframe, 23.0)
    except ValueError as exc:
        result["Thermodynamic reason"] = str(exc)
        return result
    if "Al" not in apfu.columns:
        result["Thermodynamic reason"] = "Нет Al для расчёта Altot"
        return result
    al = pd.to_numeric(apfu["Al"], errors="coerce")
    pressure = 0.5 + 0.331 * al + 0.995 * al.pow(2)
    good = al.gt(0) & np.isfinite(pressure.to_numpy(dtype=float))
    result["Al total (apfu, 23 O)"] = al
    result["P (kbar)"] = np.where(good, pressure, np.nan)
    result["P uncertainty ±16% (kbar)"] = np.where(good, pressure.abs() * 0.16, np.nan)
    result.loc[good, "Thermodynamic status"] = QC_PASS if assemblage_confirmed else QC_WARNING
    result.loc[good, "Thermodynamic reason"] = (
        "Критерии гранитной низковариантной ассоциации и amphibole-rim подтверждены."
        if assemblage_confirmed
        else "Число рассчитано, но строгие assemblage/rim критерии Mutch et al. (2016) не подтверждены."
    )
    return result


def calculate_ferry_watson_2007_ti_zircon(
    dataframe: pd.DataFrame, *, a_sio2: float, a_tio2: float
) -> pd.DataFrame:
    result = _blank_result(dataframe.index)
    if not (0 < float(a_sio2) <= 1 and 0 < float(a_tio2) <= 1):
        raise ValueError("aSiO2 и aTiO2 должны быть >0 и ≤1")
    try:
        ti, column = _trace_series(dataframe, "Ti")
    except ValueError as exc:
        result["Thermodynamic reason"] = str(exc)
        return result
    good = ti.gt(0) & np.isfinite(ti.to_numpy(dtype=float))
    denominator = 5.711 - np.log10(ti.where(good)) - math.log10(float(a_sio2)) + math.log10(float(a_tio2))
    t_k = 4800.0 / denominator
    good &= t_k.gt(0) & np.isfinite(t_k.to_numpy(dtype=float))
    result["Ti (µg/g)"] = ti
    result["Ti source column"] = column or ""
    result["aSiO2"] = float(a_sio2)
    result["aTiO2"] = float(a_tio2)
    result["T (K)"] = np.where(good, t_k, np.nan)
    result["T (°C)"] = np.where(good, t_k - 273.15, np.nan)
    result.loc[good, "Thermodynamic status"] = QC_PASS
    result.loc[good, "Thermodynamic reason"] = "Ti > 0; activities supplied explicitly."
    result.loc[~good, "Thermodynamic reason"] = result.loc[~good, "Thermodynamic reason"].replace("", "Нужен положительный Ti в µg/g (ppm).")
    return result


def calculate_loucks_2020_zircon_dfmq(
    dataframe: pd.DataFrame, *, allow_measured_u_as_initial: bool = False
) -> pd.DataFrame:
    result = _blank_result(dataframe.index)
    try:
        ce, ce_col = _trace_series(dataframe, "Ce")
        ti, ti_col = _trace_series(dataframe, "Ti")
        ui, ui_col = _trace_series(dataframe, "U", initial_u=True)
        measured_u, u_col = _trace_series(dataframe, "U")
    except ValueError as exc:
        result["Thermodynamic reason"] = str(exc)
        return result
    used_measured = False
    if ui_col is None and allow_measured_u_as_initial:
        ui = measured_u
        ui_col = u_col
        used_measured = True
    if ui_col is None:
        result["Thermodynamic reason"] = "Нужен age-corrected Ui. PetroLab не подменяет его измеренным U без явного подтверждения."
        return result
    good = ce.gt(0) & ui.gt(0) & ti.gt(0)
    ratio = ce / np.sqrt(ui * ti)
    dfmq = 3.998 * np.log10(ratio.where(good)) + 2.284
    good &= np.isfinite(dfmq.to_numpy(dtype=float))
    result["Ce (µg/g)"] = ce
    result["Ui (µg/g)"] = ui
    result["Ti (µg/g)"] = ti
    result["Ce source column"] = ce_col or ""
    result["Ui source column"] = ui_col or ""
    result["Ti source column"] = ti_col or ""
    result["ΔFMQ"] = np.where(good, dfmq, np.nan)
    result["Published SEE (log fO2)"] = 0.6
    result.loc[good, "Thermodynamic status"] = QC_WARNING if used_measured else QC_PASS
    result.loc[good, "Thermodynamic reason"] = (
        "Измеренный U использован как Ui по явному подтверждению пользователя; age correction не выполнялась."
        if used_measured
        else "Положительные Ce, Ui и Ti; применена опубликованная эмпирическая калибровка."
    )
    result.loc[~good, "Thermodynamic reason"] = result.loc[~good, "Thermodynamic reason"].replace("", "Ce, Ui и Ti должны быть положительными.")
    return result


def _melt_cation_fractions(melt: dict[str, float]) -> dict[str, float]:
    cation_moles: dict[str, float] = {}
    oxide_to_key = {
        "SiO2": "Si", "TiO2": "Ti", "Al2O3": "Al", "FeOt": "Fet", "MnO": "Mn",
        "MgO": "Mg", "CaO": "Ca", "Na2O": "Na", "K2O": "K",
    }
    for oxide, key in oxide_to_key.items():
        raw = float(melt.get(oxide, 0.0))
        if not math.isfinite(raw) or raw < 0:
            raise ValueError(f"Состав расплава: {oxide} должен быть конечным числом ≥0")
        spec = OXIDES["FeO" if oxide == "FeOt" else oxide]
        cation_moles[key] = raw / spec.molar_mass * spec.n_cation
    total = sum(cation_moles.values())
    if total <= 0:
        raise ValueError("Состав расплава пуст")
    return {key: value / total for key, value in cation_moles.items()}


def _olivine_mg_cation_fraction(dataframe: pd.DataFrame) -> pd.Series:
    allowed = ("SiO2", "FeO", "MnO", "MgO", "CaO", "NiO")
    apfu, _, _ = oxygen_normalized_apfu(dataframe, 4.0, allowed_oxides=allowed)
    cations = [column for column in ("Si", "Fe2", "Fe3", "Mn", "Mg", "Ca", "Ni") if column in apfu.columns]
    total = apfu[cations].sum(axis=1, min_count=1)
    return apfu.get("Mg", pd.Series(np.nan, index=dataframe.index)) / total.replace(0, np.nan)


def calculate_putirka_2008_ol_liq_eq22(
    dataframe: pd.DataFrame,
    *,
    melt: dict[str, float],
    pressure_kbar: float,
    equilibrium_confirmed: bool,
) -> pd.DataFrame:
    result = _blank_result(dataframe.index)
    pressure = float(pressure_kbar)
    if not math.isfinite(pressure) or pressure < 0:
        raise ValueError("Давление должно быть конечным числом ≥0 kbar")
    try:
        liq = _melt_cation_fractions(melt)
        mg_ol = _olivine_mg_cation_fraction(dataframe)
    except ValueError as exc:
        result["Thermodynamic reason"] = str(exc)
        return result
    if liq.get("Mg", 0.0) <= 0 or liq.get("Si", 0.0) <= 0:
        result["Thermodynamic reason"] = "Для Eq. 22 расплав должен содержать положительные MgO и SiO2."
        return result
    d_mg = mg_ol / liq["Mg"]
    cnml = liq.get("Mg", 0.0) + liq.get("Fet", 0.0) + liq.get("Ca", 0.0) + liq.get("Mn", 0.0)
    if cnml <= 0 or liq.get("Al", 0.0) >= 1 or liq.get("Ti", 0.0) >= 1:
        result["Thermodynamic reason"] = "Невалидные cation fractions расплава для Eq. 22."
        return result
    nf = 3.5 * math.log(1.0 - liq.get("Al", 0.0)) + 7.0 * math.log(1.0 - liq.get("Ti", 0.0))
    h2o = float(melt.get("H2O", 0.0))
    if not math.isfinite(h2o) or h2o < 0:
        raise ValueError("H2O расплава должен быть конечным числом ≥0 wt%")
    p_gpa = 0.1 * pressure
    numerator = 15294.6 + 1318.8 * p_gpa + 2.48348 * p_gpa**2
    denominator = (
        8.048 + 2.8352 * np.log(d_mg.where(d_mg.gt(0)))
        + 2.097 * math.log(1.5 * cnml)
        + 2.575 * math.log(3.0 * liq["Si"])
        - 1.41 * nf + 0.222 * h2o + 0.5 * p_gpa
    )
    t_k = numerator / denominator + 273.15
    good = d_mg.gt(0) & t_k.gt(0) & np.isfinite(t_k.to_numpy(dtype=float))
    result["DMg ol/melt"] = d_mg
    result["P assumption (kbar)"] = pressure
    result["H2O melt (wt%)"] = h2o
    result["T (K)"] = np.where(good, t_k, np.nan)
    result["T (°C)"] = np.where(good, t_k - 273.15, np.nan)
    result.loc[good, "Thermodynamic status"] = QC_PASS if equilibrium_confirmed else QC_WARNING
    result.loc[good, "Thermodynamic reason"] = (
        "Пара olivine–melt подтверждена пользователем; Eq. 22 рассчитано."
        if equilibrium_confirmed
        else "Eq. 22 рассчитано, но равновесие/cogenetic relation olivine–melt не подтверждено."
    )
    result.loc[~good, "Thermodynamic reason"] = result.loc[~good, "Thermodynamic reason"].replace("", "Невалидный DMg или математический результат Eq. 22.")
    return result


def calculate_method(
    method_id: str,
    dataframe: pd.DataFrame,
    *,
    assumptions: dict[str, Any] | None = None,
    melt: dict[str, float] | None = None,
) -> pd.DataFrame:
    cfg = dict(assumptions or {})
    method = method_by_id(method_id)
    if method.method_id == PUTIRKA_2008_CPX_ONLY.method_id:
        legacy = calculate_putirka_2008_cpx_only_t32d(
            dataframe,
            pressure_kbar=float(cfg.get("pressure_kbar", 0.0)),
            applicability_confirmed=bool(cfg.get("applicability_confirmed", False)),
        ).copy()
        return legacy.rename(columns={
            "Thermobarometry status": "Thermodynamic status",
            "Thermobarometry reason": "Thermodynamic reason",
        })
    if method.method_id == PUTIRKA_2016_AMP_EQ5.method_id:
        return calculate_putirka_2016_amp_eq5(
            dataframe, applicability_confirmed=bool(cfg.get("applicability_confirmed", False))
        )
    if method.method_id == MUTCH_2016_AMP_BAROMETER.method_id:
        return calculate_mutch_2016_amp_barometer(
            dataframe, assemblage_confirmed=bool(cfg.get("assemblage_confirmed", False))
        )
    if method.method_id == FERRY_WATSON_2007_TI_ZIRCON.method_id:
        return calculate_ferry_watson_2007_ti_zircon(
            dataframe,
            a_sio2=float(cfg.get("a_sio2", 1.0)),
            a_tio2=float(cfg.get("a_tio2", 1.0)),
        )
    if method.method_id == LOUCKS_2020_ZIRCON_DFMQ.method_id:
        return calculate_loucks_2020_zircon_dfmq(
            dataframe,
            allow_measured_u_as_initial=bool(cfg.get("allow_measured_u_as_initial", False)),
        )
    if method.method_id == PUTIRKA_2008_OL_LIQ_EQ22.method_id:
        if melt is None:
            raise ValueError("Для mineral–melt расчёта нужен состав расплава")
        return calculate_putirka_2008_ol_liq_eq22(
            dataframe,
            melt=melt,
            pressure_kbar=float(cfg.get("pressure_kbar", 0.0)),
            equilibrium_confirmed=bool(cfg.get("equilibrium_confirmed", False)),
        )
    raise ValueError("Для метода нет calculator implementation")


@dataclass(frozen=True)
class ThermodynamicRun:
    id: int
    project_id: int
    method_id: str
    method_title: str
    input_mode: str
    parameter_kind: str
    input_analysis_ids: tuple[str, ...]
    assumptions: dict[str, Any]
    melt: dict[str, Any]
    results: tuple[dict[str, Any], ...]
    calculated_at: str
    is_current: bool


def ensure_thermodynamic_storage() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS thermodynamic_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                method_id TEXT NOT NULL,
                method_title TEXT NOT NULL,
                input_mode TEXT NOT NULL,
                parameter_kind TEXT NOT NULL,
                input_analysis_ids_json TEXT NOT NULL,
                source_fingerprints_json TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                melt_json TEXT NOT NULL,
                results_json TEXT NOT NULL,
                calculated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_thermodynamic_project ON thermodynamic_runs(project_id, id DESC)"
        )
        con.commit()


def _fingerprints(project_id: int, analysis_ids: tuple[str, ...]) -> dict[str, str]:
    if not analysis_ids:
        return {}
    marks = ",".join("?" for _ in analysis_ids)
    with connect() as con:
        rows = con.execute(
            f"""SELECT a.analysis_id, a.data_json
                FROM analysis_rows a
                JOIN project_dataset_links l ON l.dataset_id=a.dataset_id
                WHERE l.project_id=? AND a.analysis_id IN ({marks})""",
            (int(project_id), *analysis_ids),
        ).fetchall()
    found: dict[str, str] = {}
    for row in rows:
        try:
            payload = json.loads(str(row["data_json"]))
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            found[str(row["analysis_id"])] = source_row_fingerprint(payload)
    missing = [value for value in analysis_ids if value not in found]
    if missing:
        raise ValueError("Часть входных анализов недоступна в рабочем контексте проекта")
    return found


def save_thermodynamic_run(
    project_id: int,
    *,
    method_id: str,
    source_dataframe: pd.DataFrame,
    results_dataframe: pd.DataFrame,
    assumptions: dict[str, Any] | None = None,
    melt: dict[str, Any] | None = None,
) -> ThermodynamicRun:
    ensure_thermodynamic_storage()
    method = method_by_id(method_id)
    if "_analysis_id" not in source_dataframe.columns:
        raise ValueError("Для сохранения требуются неизменяемые _analysis_id")
    if len(source_dataframe) != len(results_dataframe):
        raise ValueError("Число результатов не соответствует числу входных анализов")
    ids = tuple(source_dataframe["_analysis_id"].astype(str).tolist())
    if not ids or len(set(ids)) != len(ids):
        raise ValueError("Входные _analysis_id должны быть непустыми и уникальными")
    fps = _fingerprints(int(project_id), ids)
    records = results_dataframe.copy().reset_index(drop=True)
    records.insert(0, "_analysis_id", ids)
    now = _utcnow()
    assumptions_safe = _json_safe_record(dict(assumptions or {}))
    melt_safe = _json_safe_record(dict(melt or {}))
    with connect() as con:
        cur = con.execute(
            """INSERT INTO thermodynamic_runs(
                project_id,method_id,method_title,input_mode,parameter_kind,
                input_analysis_ids_json,source_fingerprints_json,assumptions_json,melt_json,
                results_json,calculated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                int(project_id), method.method_id, method.title, method.input_mode, method.parameter_kind,
                json.dumps(ids, ensure_ascii=False), json.dumps(fps, ensure_ascii=False, sort_keys=True),
                json.dumps(assumptions_safe, ensure_ascii=False, sort_keys=True),
                json.dumps(melt_safe, ensure_ascii=False, sort_keys=True),
                json.dumps([_json_safe_record(row) for row in records.to_dict("records")], ensure_ascii=False),
                now,
            ),
        )
        con.commit()
        run_id = int(cur.lastrowid)
    return ThermodynamicRun(
        run_id, int(project_id), method.method_id, method.title, method.input_mode,
        method.parameter_kind, ids, dict(assumptions or {}), dict(melt or {}),
        tuple(records.to_dict("records")), now, True,
    )


def _is_current(project_id: int, ids: tuple[str, ...], saved: dict[str, str]) -> bool:
    try:
        return _fingerprints(project_id, ids) == saved
    except ValueError:
        return False


def list_thermodynamic_runs(project_id: int) -> list[ThermodynamicRun]:
    ensure_thermodynamic_storage()
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM thermodynamic_runs WHERE project_id=? ORDER BY id DESC", (int(project_id),)
        ).fetchall()
    runs: list[ThermodynamicRun] = []
    for row in rows:
        try:
            ids = tuple(str(value) for value in json.loads(str(row["input_analysis_ids_json"])))
            fps = {str(k): str(v) for k, v in json.loads(str(row["source_fingerprints_json"])).items()}
            assumptions = dict(json.loads(str(row["assumptions_json"])))
            melt = dict(json.loads(str(row["melt_json"])))
            results = tuple(dict(value) for value in json.loads(str(row["results_json"])))
        except (TypeError, ValueError, json.JSONDecodeError, AttributeError):
            continue
        runs.append(ThermodynamicRun(
            id=int(row["id"]), project_id=int(row["project_id"]), method_id=str(row["method_id"]),
            method_title=str(row["method_title"]), input_mode=str(row["input_mode"]),
            parameter_kind=str(row["parameter_kind"]), input_analysis_ids=ids,
            assumptions=assumptions, melt=melt, results=results, calculated_at=str(row["calculated_at"]),
            is_current=_is_current(int(row["project_id"]), ids, fps),
        ))
    return runs


def thermodynamic_records_for_analysis(project_id: int, analysis_id: str) -> list[dict[str, Any]]:
    """Return newest-first saved thermodynamic history for one immutable analysis ID."""
    wanted = str(analysis_id)
    records: list[dict[str, Any]] = []
    for run in list_thermodynamic_runs(int(project_id)):
        for row in run.results:
            if str(row.get("_analysis_id", "")) != wanted:
                continue
            item = dict(row)
            item.update({
                "run_id": run.id,
                "method_id": run.method_id,
                "Метод": run.method_title,
                "Тип": run.parameter_kind,
                "Режим": run.input_mode,
                "Актуальность": "Актуален" if run.is_current else "Требует пересчёта",
                "Рассчитано": run.calculated_at,
            })
            records.append(item)
    # Backward-compatible visibility of runs saved before the generic thermodynamic layer.
    try:
        from petrolab.thermobarometry import list_runs as list_legacy_runs
        for run in list_legacy_runs(int(project_id)):
            for row in run.results:
                if str(row.get("_analysis_id", "")) != wanted:
                    continue
                item = dict(row)
                item.update({
                    "run_id": f"legacy-{run.id}",
                    "method_id": run.method_id,
                    "Метод": run.method_title,
                    "Тип": KIND_TEMPERATURE,
                    "Режим": MODE_SINGLE_MINERAL,
                    "Актуальность": "Актуален" if run.is_current else "Требует пересчёта",
                    "Рассчитано": run.calculated_at,
                })
                records.append(item)
    except Exception:
        pass
    return records
