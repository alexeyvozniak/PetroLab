"""Versioned thermobarometry runs; raw analyses are never overwritten.

The first calculator is deliberately narrow.  It establishes the persistence,
input/QC and provenance contract needed for the larger mineral-pair and
mineral-liquid catalogue without presenting an unqualified ``P–T`` button.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from petrolab.analysis_identity import source_row_fingerprint
from petrolab.db import _json_safe_record, _utcnow, connect
from petrolab.minerals.formulae import OXIDES
from petrolab.scientific_contracts import ThermobarometerMethod, validate_thermobarometer_registry


QC_PASS = "PASS"
QC_FAIL = "FAIL"
QC_INSUFFICIENT_INPUT = "INSUFFICIENT_INPUT"
QC_OUTSIDE_CALIBRATION = "OUTSIDE_CALIBRATION"
QC_NOT_APPLICABLE = "NOT_APPLICABLE"
QC_WARNING = "WARNING"
QC_STATUSES = (QC_PASS, QC_WARNING, QC_FAIL, QC_INSUFFICIENT_INPUT, QC_OUTSIDE_CALIBRATION, QC_NOT_APPLICABLE)

PUTIRKA_2008_CPX_T32D = ThermobarometerMethod(
    method_id="putirka_2008_cpx_only_t32d",
    title="Putirka (2008) · Cpx-only thermometer · Eq. 32d",
    equation_version="Published Eq. 32d; PetroLab implementation 1.0.0",
    source_citation="Putirka, K.D. (2008). Thermometers and Barometers for Volcanic Systems. "
    "Reviews in Mineralogy and Geochemistry 69, 61–120.",
    source_doi="10.2138/rmg.2008.69.3",
    required_components=("SiO2", "TiO2", "Al2O3", "Cr2O3", "FeOt", "MgO", "CaO", "Na2O", "K2O"),
    calibration_range="Anhydrous clinopyroxene thermometer; pressure must be supplied independently. "
    "Do not use it as a hydrous Cpx thermometer or as an automatic equilibrium test.",
    uncertainty="SEE ±58 °C for anhydrous data; ±87 °C reported for hydrous data.",
    equilibrium_test="PetroLab asks for petrographic applicability confirmation and flags "
    "cation sums outside 3.99–4.02 (6 O screening after Neave & Putirka, 2017).",
    assumptions="Total Fe is required as FeOt (FeO-equivalent). Pressure is a recorded user assumption; "
    "the result is a temperature, not an independent P–T solution.",
)

THERMOBAROMETER_REGISTRY = (PUTIRKA_2008_CPX_T32D,)
validate_thermobarometer_registry(THERMOBAROMETER_REGISTRY)


@dataclass(frozen=True)
class ThermobarometryRun:
    id: int
    project_id: int
    method_id: str
    method_title: str
    status: str
    input_analysis_ids: tuple[str, ...]
    assumptions: dict[str, Any]
    results: tuple[dict[str, Any], ...]
    calculated_at: str
    is_current: bool


def methods() -> tuple[ThermobarometerMethod, ...]:
    return THERMOBAROMETER_REGISTRY


def method_by_id(method_id: str) -> ThermobarometerMethod:
    for method in THERMOBAROMETER_REGISTRY:
        if method.method_id == str(method_id):
            return method
    raise ValueError("Калибровка не зарегистрирована в PetroLab")


def ensure_thermobarometry_storage() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS thermobarometry_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                method_id TEXT NOT NULL,
                method_title TEXT NOT NULL,
                status TEXT NOT NULL,
                input_analysis_ids_json TEXT NOT NULL,
                source_fingerprints_json TEXT NOT NULL,
                assumptions_json TEXT NOT NULL,
                results_json TEXT NOT NULL,
                calculated_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_thermobarometry_project ON thermobarometry_runs(project_id, id DESC)"
        )
        con.commit()


def _finite_column(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(False, index=dataframe.index, dtype=bool)
    values = pd.to_numeric(dataframe[column], errors="coerce")
    return values.notna() & np.isfinite(values.to_numpy(dtype=float))


def _oxide_frame(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Use only the published FeOt basis; no implicit Fe3+/Fe2+ reconstruction."""
    required = PUTIRKA_2008_CPX_T32D.required_components
    work = pd.DataFrame(index=dataframe.index)
    for column in required:
        if column == "FeOt":
            source = "FeOt"
        else:
            source = column
        if source in dataframe.columns:
            work[column] = pd.to_numeric(dataframe[source], errors="coerce")
        else:
            work[column] = np.nan
    return work


def _cpx_components(oxides: pd.DataFrame) -> pd.DataFrame:
    """Cations on six oxygens and Eq. 32d enstatite activity.

    This is the published total-Fe (FeOt) cation basis used by the calibration,
    kept here rather than borrowing an active structural-formula result with a
    potentially different Fe policy.
    """
    cation_counts = {"SiO2": 1, "TiO2": 1, "Al2O3": 2, "Cr2O3": 2, "FeOt": 1,
                      "MgO": 1, "CaO": 1, "Na2O": 2, "K2O": 2}
    oxygen_counts = {"SiO2": 2, "TiO2": 2, "Al2O3": 3, "Cr2O3": 3, "FeOt": 1,
                     "MgO": 1, "CaO": 1, "Na2O": 1, "K2O": 1}
    molar_masses = {**{key: value.molar_mass for key, value in OXIDES.items()}, "FeOt": OXIDES["FeO"].molar_mass}
    moles = pd.DataFrame({key: oxides[key] / molar_masses[key] for key in oxides.columns}, index=oxides.index)
    oxygen_total = sum(moles[key] * oxygen_counts[key] for key in moles.columns)
    factor = 6.0 / oxygen_total
    cats = pd.DataFrame({key: moles[key] * cation_counts[key] * factor for key in moles.columns}, index=oxides.index)
    cats = cats.rename(columns={
        "SiO2": "Si", "TiO2": "Ti", "Al2O3": "Al", "Cr2O3": "Cr", "FeOt": "FeT",
        "MgO": "Mg", "CaO": "Ca", "Na2O": "Na", "K2O": "K",
    })
    cats["AlIV"] = (2.0 - cats["Si"]).clip(lower=0.0)
    cats["AlVI"] = (cats["Al"] - cats["AlIV"]).clip(lower=0.0)
    cats["a_En"] = (
        (1.0 - cats["Ca"] - cats["Na"] - cats["K"])
        * (1.0 - 0.5 * (cats["Al"] + cats["Cr"] + cats["Na"] + cats["K"]))
    )
    cats["Cation sum (6 O)"] = cats[["Si", "Ti", "Al", "Cr", "FeT", "Mg", "Ca", "Na", "K"]].sum(axis=1)
    return cats


def calculate_putirka_2008_cpx_only_t32d(
    dataframe: pd.DataFrame,
    *,
    pressure_kbar: float,
    applicability_confirmed: bool,
) -> pd.DataFrame:
    """Calculate T for Cpx rows without replacing their raw or formula columns.

    Negative finite Cr2O3 values are treated as analytical below-zero noise and are
    floored to 0 wt.% only in the calculation frame. The raw analysis is preserved
    and the calculated row is marked WARNING. Components outside Eq. 32d (for
    example P2O5) are deliberately ignored by this calculator.
    """
    pressure = float(pressure_kbar)
    if not math.isfinite(pressure) or pressure < 0:
        raise ValueError("Давление должно быть конечным числом ≥ 0 kbar")
    result = pd.DataFrame(index=dataframe.index)
    result["Thermobarometry status"] = QC_INSUFFICIENT_INPUT
    result["Thermobarometry reason"] = ""
    result["P assumption (kbar)"] = pressure
    result["T (K)"] = np.nan
    result["T (°C)"] = np.nan
    result["Published SEE (°C)"] = 58.0

    applicability_warning = not applicability_confirmed

    raw_oxides = _oxide_frame(dataframe)
    finite = pd.DataFrame(
        {column: _finite_column(raw_oxides, column) for column in raw_oxides.columns},
        index=dataframe.index,
    )
    calculation_oxides = raw_oxides.copy()
    negative_cr = finite["Cr2O3"] & pd.to_numeric(raw_oxides["Cr2O3"], errors="coerce").lt(0)
    calculation_oxides.loc[negative_cr, "Cr2O3"] = 0.0

    nonnegative = pd.DataFrame(
        {
            column: pd.to_numeric(calculation_oxides[column], errors="coerce").ge(0)
            for column in calculation_oxides.columns
        },
        index=dataframe.index,
    )
    usable = finite.all(axis=1) & nonnegative.all(axis=1)
    for index in dataframe.index[~usable]:
        missing = [column for column in raw_oxides.columns if not bool(finite.at[index, column])]
        negative = [
            column
            for column in calculation_oxides.columns
            if bool(finite.at[index, column]) and not bool(nonnegative.at[index, column])
        ]
        parts = []
        if missing:
            parts.append("нет/нечисловые: " + ", ".join(missing))
        if negative:
            parts.append("отрицательные: " + ", ".join(negative))
        result.at[index, "Thermobarometry reason"] = "; ".join(parts)

    if usable.any():
        components = _cpx_components(calculation_oxides.loc[usable])
        result.loc[usable, "Cation sum (6 O)"] = components["Cation sum (6 O)"]
        result.loc[usable, "a_En"] = components["a_En"]
        valid_activity = components["a_En"].gt(0) & np.isfinite(components["a_En"])
        activity_index = components.index[valid_activity]
        if len(activity_index):
            value = components.loc[activity_index]
            denominator = (
                61.1 + 36.6 * value["Ti"] + 10.9 * value["FeT"]
                - 0.95 * (value["Al"] + value["Cr"] - value["Na"] - value["K"])
                + 0.395 * np.log(value["a_En"]) ** 2
            )
            temperature_k = (93100.0 + 544.0 * pressure) / denominator
            calculation_ok = np.isfinite(temperature_k) & temperature_k.gt(0)
            good_index = temperature_k.index[calculation_ok]
            result.loc[good_index, "T (K)"] = temperature_k.loc[good_index]
            result.loc[good_index, "T (°C)"] = temperature_k.loc[good_index] - 273.15
            cation_ok = value.loc[good_index, "Cation sum (6 O)"].between(3.99, 4.02, inclusive="both")
            passing = good_index[cation_ok]
            failing = good_index[~cation_ok]
            result.loc[passing, "Thermobarometry status"] = QC_WARNING if applicability_warning else QC_PASS
            result.loc[passing, "Thermobarometry reason"] = (
                "Входы полны; cation-sum screen 3.99–4.02 пройден. " +
                ("Применимость метода не подтверждена; результат сохранён с предупреждением." if applicability_warning else "")
            ).strip()
            result.loc[failing, "Thermobarometry status"] = QC_FAIL
            result.loc[failing, "Thermobarometry reason"] = (
                "Cation-sum screen 3.99–4.02 не пройден; число показано только для диагностики. " +
                ("Применимость метода также не подтверждена." if applicability_warning else "")
            ).strip()
            bad_math = activity_index[~calculation_ok]
            result.loc[bad_math, "Thermobarometry reason"] = "Невалидный математический результат Eq. 32d."
        invalid_activity = components.index[~valid_activity]
        result.loc[invalid_activity, "Thermobarometry reason"] = "a_En ≤ 0; Eq. 32d неприменимо."

    for index in dataframe.index[negative_cr]:
        raw_value = float(raw_oxides.at[index, "Cr2O3"])
        note = (
            f"Cr2O3={raw_value:g} wt.% в исходном анализе; для Eq. 32d использовано 0 wt.% "
            "как физическая нижняя граница, исходные данные не изменены."
        )
        existing = str(result.at[index, "Thermobarometry reason"] or "").strip()
        result.at[index, "Thermobarometry reason"] = f"{existing} {note}".strip()
        if result.at[index, "Thermobarometry status"] == QC_PASS:
            result.at[index, "Thermobarometry status"] = QC_WARNING
    return result


def _input_fingerprints(project_id: int, analysis_ids: tuple[str, ...]) -> dict[str, str]:
    with connect() as con:
        rows = con.execute(
            """SELECT a.analysis_id, a.data_json
               FROM analysis_rows a
               JOIN project_dataset_links link ON link.dataset_id=a.dataset_id
               WHERE link.project_id=? AND a.analysis_id IN ({})""".format(",".join("?" for _ in analysis_ids)),
            (int(project_id), *analysis_ids),
        ).fetchall()
    found: dict[str, str] = {}
    for row in rows:
        try:
            payload = json.loads(str(row["data_json"]))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            found[str(row["analysis_id"])] = source_row_fingerprint(payload)
    missing = [analysis_id for analysis_id in analysis_ids if analysis_id not in found]
    if missing:
        raise ValueError("Часть входных анализов недоступна в рабочем контексте проекта")
    return found


def save_run(
    project_id: int,
    *,
    method_id: str,
    source_dataframe: pd.DataFrame,
    results_dataframe: pd.DataFrame,
    assumptions: dict[str, Any],
) -> ThermobarometryRun:
    ensure_thermobarometry_storage()
    method = method_by_id(method_id)
    if "_analysis_id" not in source_dataframe.columns:
        raise ValueError("Для термобарометрии требуются неизменяемые _analysis_id")
    if len(source_dataframe) != len(results_dataframe):
        raise ValueError("Результаты термобарометрии не соответствуют числу входных анализов")
    analysis_ids = tuple(source_dataframe["_analysis_id"].astype(str).tolist())
    if not analysis_ids or len(set(analysis_ids)) != len(analysis_ids):
        raise ValueError("Входные _analysis_id должны быть непустыми и уникальными")
    fingerprints = _input_fingerprints(int(project_id), analysis_ids)
    summary_status = (
        QC_PASS if (results_dataframe["Thermobarometry status"] == QC_PASS).any()
        else QC_WARNING if (results_dataframe["Thermobarometry status"] == QC_WARNING).any()
        else QC_FAIL
    )
    now = _utcnow()
    records = results_dataframe.copy()
    records.insert(0, "_analysis_id", analysis_ids)
    with connect() as con:
        cur = con.execute(
            """INSERT INTO thermobarometry_runs(
                    project_id, method_id, method_title, status, input_analysis_ids_json,
                    source_fingerprints_json, assumptions_json, results_json, calculated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                int(project_id), method.method_id, method.title, summary_status,
                json.dumps(analysis_ids, ensure_ascii=False), json.dumps(fingerprints, ensure_ascii=False, sort_keys=True),
                json.dumps(_json_safe_record(assumptions), ensure_ascii=False, sort_keys=True),
                json.dumps([_json_safe_record(row) for row in records.to_dict("records")], ensure_ascii=False), now,
            ),
        )
        con.commit()
        run_id = int(cur.lastrowid)
    return ThermobarometryRun(run_id, int(project_id), method.method_id, method.title, summary_status,
                              analysis_ids, dict(assumptions), tuple(records.to_dict("records")), now, True)


def _run_current(project_id: int, analysis_ids: tuple[str, ...], fingerprints: dict[str, str]) -> bool:
    try:
        return _input_fingerprints(project_id, analysis_ids) == fingerprints
    except ValueError:
        return False


def list_runs(project_id: int) -> list[ThermobarometryRun]:
    ensure_thermobarometry_storage()
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM thermobarometry_runs WHERE project_id=? ORDER BY id DESC", (int(project_id),)
        ).fetchall()
    result: list[ThermobarometryRun] = []
    for row in rows:
        try:
            analysis_ids = tuple(str(value) for value in json.loads(str(row["input_analysis_ids_json"])))
            fingerprints = {str(key): str(value) for key, value in json.loads(str(row["source_fingerprints_json"])).items()}
            assumptions = dict(json.loads(str(row["assumptions_json"])))
            records = tuple(dict(record) for record in json.loads(str(row["results_json"])))
        except (TypeError, ValueError, json.JSONDecodeError, AttributeError):
            continue
        result.append(ThermobarometryRun(
            id=int(row["id"]), project_id=int(row["project_id"]), method_id=str(row["method_id"]),
            method_title=str(row["method_title"]), status=str(row["status"]), input_analysis_ids=analysis_ids,
            assumptions=assumptions, results=records, calculated_at=str(row["calculated_at"]),
            is_current=_run_current(int(row["project_id"]), analysis_ids, fingerprints),
        ))
    return result
