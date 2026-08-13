from __future__ import annotations

import numpy as np
import pandas as pd

from petrolab.minerals.classification import (
    FIELD_COL, LEVEL_COL, METHOD_COL, NOTE_COL, SPECIES_COL, attach_mineral_classification,
)
from petrolab.minerals.formulae import CalculationResult, HALOGENS, OXIDES, calculate_formula
from petrolab.minerals.garnet_ti import apply_strict_grew_figure5
from petrolab.minerals.registry import MINERALS

FE2O3T_TO_FEOT = 2.0 * OXIDES["FeO"].molar_mass / OXIDES["Fe2O3"].molar_mass
FORMULA_INPUT_STATUS_COL = "QC formula input"
FORMULA_MISSING_INPUTS_COL = "Formula missing inputs"


def prepare_formula_input(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    work = dataframe.copy()
    if "Fe2O3t" not in work.columns:
        return work, ""
    total = pd.to_numeric(work["Fe2O3t"], errors="coerce")
    present = total.notna()
    if not present.any():
        return work.drop(columns=["Fe2O3t"]), ""
    conflicts: list[str] = []
    for column in ("FeO", "FeOt", "Fe2O3"):
        if column in work and (present & pd.to_numeric(work[column], errors="coerce").notna()).any():
            conflicts.append(column)
    if conflicts:
        raise ValueError(
            "Fe2O3t (ΣFe как Fe2O3) одновременно задан с " + ", ".join(conflicts)
            + ". Нельзя определить источник total Fe однозначно."
        )
    converted = total * FE2O3T_TO_FEOT
    if "FeOt" in work:
        work["FeOt"] = pd.to_numeric(work["FeOt"], errors="coerce").combine_first(converted)
    else:
        work["FeOt"] = converted
    work = work.drop(columns=["Fe2O3t"])
    return work, (
        "Fe2O3t интерпретирован как ΣFe на базе Fe2O3 и перед расчётом переведён в FeOt "
        f"с коэффициентом {FE2O3T_TO_FEOT:.8f}; это не задаёт Fe³⁺/Fe²⁺."
    )


def _classification_unavailable(dataframe: pd.DataFrame, error: ValueError) -> pd.DataFrame:
    result = dataframe.copy()
    result[SPECIES_COL] = ""
    result[FIELD_COL] = "Автоматическая классификация недоступна для этих входных данных"
    result[LEVEL_COL] = "insufficient classification inputs"
    result[METHOD_COL] = ""
    result[NOTE_COL] = str(error)
    return result


def _align(source: pd.DataFrame, calculated: pd.DataFrame) -> pd.DataFrame:
    if len(source) != len(calculated):
        raise ValueError("Число строк результата формулы не совпадает с исходными анализами")
    if "_analysis_id" in source.columns:
        if "_analysis_id" not in calculated.columns:
            raise ValueError("Результат формулы потерял _analysis_id")
        source_ids = source["_analysis_id"].astype(str)
        result = calculated.copy()
        result_ids = result["_analysis_id"].astype(str)
        if source_ids.duplicated().any() or result_ids.duplicated().any():
            raise ValueError("Повторяющиеся _analysis_id не позволяют безопасно выровнять формулу")
        if set(source_ids) != set(result_ids):
            raise ValueError("Набор _analysis_id результата формулы не совпадает с источником")
        result["_analysis_id"] = result_ids
        result = result.set_index("_analysis_id", drop=False).loc[source_ids.tolist()].copy()
        result.index = source.index
        return result
    if not source.index.is_unique or not calculated.index.is_unique:
        raise ValueError("Без _analysis_id для выравнивания требуется уникальный pandas index")
    if set(source.index) != set(calculated.index):
        raise ValueError("Calculator изменил набор строк и не вернул _analysis_id")
    return calculated.loc[source.index].copy()


def _presence(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(False, index=dataframe.index, dtype=bool)
    return pd.to_numeric(dataframe[column], errors="coerce").notna()


def _restore_missing_semantics(result: pd.DataFrame, original: pd.DataFrame, mineral_key: str) -> pd.DataFrame:
    out = result.copy()
    module = MINERALS.get(str(mineral_key))
    typical = tuple(module.typical_oxides) if module is not None else tuple(OXIDES) + tuple(HALOGENS)
    supplied = [column for column in typical if column in original.columns]
    missing: dict[object, list[str]] = {index: [] for index in original.index}
    for column in supplied:
        present = _presence(original, column)
        for index in original.index[~present]:
            missing[index].append(column)

    for oxide, spec in OXIDES.items():
        output = f"apfu_{spec.cation}"
        if oxide in original.columns and output in out.columns:
            out.loc[~_presence(original, oxide), output] = np.nan
    fe_sources = [column for column in ("FeO", "FeOt", "Fe2O3t") if column in original.columns]
    if fe_sources and "apfu_Fe2" in out.columns:
        present = pd.Series(False, index=original.index, dtype=bool)
        for column in fe_sources:
            present |= _presence(original, column)
        out.loc[~present, "apfu_Fe2"] = np.nan
    for halogen in HALOGENS:
        output = f"apfu_{halogen}"
        if halogen in original.columns and output in out.columns:
            out.loc[~_presence(original, halogen), output] = np.nan

    status = pd.Series("полный набор в представленных колонках", index=original.index, dtype="string")
    missing_text = pd.Series("", index=original.index, dtype="string")
    for index, columns in missing.items():
        if columns:
            status.at[index] = "частичный аналитический набор: есть пропуски в строке"
            missing_text.at[index] = ", ".join(columns)
    out[FORMULA_INPUT_STATUS_COL] = status
    out[FORMULA_MISSING_INPUTS_COL] = missing_text
    return out


def _guard_apatite_classification(final: pd.DataFrame) -> pd.DataFrame:
    if "OH_est_basis" not in final.columns:
        return final
    unresolved = final["OH_est_basis"].astype(str) != "F и Cl измерены"
    if not unresolved.any():
        return final
    out = final.copy()
    out.loc[unresolved, SPECIES_COL] = ""
    out.loc[unresolved, FIELD_COL] = "Apatite X-anion field unresolved"
    out.loc[unresolved, LEVEL_COL] = "insufficient X-anion data"
    out.loc[unresolved, METHOD_COL] = "Pasero et al. (2010) apatite-supergroup anion dominance"
    out.loc[unresolved, NOTE_COL] = "F и Cl должны быть измерены в этой строке для оценки OH и X-anion dominance."
    return out


def calculate_formula_safe(dataframe: pd.DataFrame, mineral_key: str, method_id: str | None = None) -> CalculationResult:
    prepared, preparation_note = prepare_formula_input(dataframe)
    result = calculate_formula(prepared, mineral_key, method_id)
    aligned = _align(prepared, result.data)

    final = dataframe.copy()
    for column in aligned.columns:
        if column not in prepared.columns:
            final[column] = aligned[column]
    final = _restore_missing_semantics(final, dataframe, mineral_key)

    try:
        final = attach_mineral_classification(final, mineral_key, method_id)
        if str(mineral_key) == "garnet":
            final = apply_strict_grew_figure5(final)
    except ValueError as exc:
        final = _classification_unavailable(final, exc)
    if str(mineral_key) == "apatite":
        final = _guard_apatite_classification(final)

    notes = [text for text in (preparation_note, result.note_ru) if text]
    return CalculationResult(final, "\n\n".join(notes))
