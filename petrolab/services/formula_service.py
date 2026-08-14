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
FORMULA_VALID_COL = "formula_valid"
FORMULA_INVALID_REASON_COL = "formula_invalid_reason"
FORMULA_INPUT_POLICY_COL = "Formula input policy"
FORMULA_INPUTS_USED_COL = "Formula inputs used"

_CRITICAL_ROW_INPUTS: dict[str, tuple[str, ...]] = {
    "mica": ("SiO2", "Al2O3", "MgO", "K2O"),
    "amphibole": ("SiO2", "Al2O3", "MgO", "CaO", "Na2O"),
    "clinopyroxene": ("SiO2", "MgO", "CaO"),
    "orthopyroxene": ("SiO2", "MgO"),
    "olivine": ("SiO2", "MgO"),
    "garnet": ("SiO2", "Al2O3", "MgO", "CaO"),
    "feldspar": ("SiO2", "Al2O3", "Na2O", "K2O", "CaO"),
    "nepheline": ("SiO2", "Al2O3", "Na2O", "K2O"),
    "carbonate": ("CaO", "MgO"),
    "spinel": ("MgO",),
    "fe_ti_oxide": ("TiO2",),
    "perovskite": ("TiO2", "CaO"),
    "apatite": ("P2O5", "CaO"),
    "titanite": ("SiO2", "TiO2", "CaO"),
    "zircon": ("SiO2", "ZrO2"),
}
_FE_COLUMNS = ("FeO", "FeOt", "Fe2O3", "Fe2O3t")
_FE_REQUIRED_MINERALS = {
    "mica", "amphibole", "clinopyroxene", "orthopyroxene", "olivine",
    "garnet", "spinel", "fe_ti_oxide",
}
_GARNET_OMITTED_Y = ("Ti", "Zr", "Hf", "V3", "Nb", "Sn", "U")


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
    values = pd.to_numeric(dataframe[column], errors="coerce")
    return values.notna() & np.isfinite(values.to_numpy(dtype=float))


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

    halogen_hole = pd.Series(False, index=original.index, dtype=bool)
    for halogen in ("F", "Cl"):
        if halogen in original.columns:
            halogen_hole |= ~_presence(original, halogen)
    if halogen_hole.any():
        for dependent in ("apfu_OH_max", "apfu_OH_est"):
            if dependent in out.columns:
                out.loc[halogen_hole, dependent] = np.nan
        if "QC_Z_site" in out.columns:
            out.loc[halogen_hole, "QC_Z_site"] = "не рассчитано: пропуск F/Cl"

    status = pd.Series("полный набор в представленных колонках", index=original.index, dtype="string")
    missing_text = pd.Series("", index=original.index, dtype="string")
    for index, columns in missing.items():
        if columns:
            status.at[index] = "частичный аналитический набор: есть пропуски в строке"
            missing_text.at[index] = ", ".join(columns)
    out[FORMULA_INPUT_STATUS_COL] = status
    out[FORMULA_MISSING_INPUTS_COL] = missing_text
    return out


def _critical_row_validity(original: pd.DataFrame, mineral_key: str) -> tuple[pd.Series, pd.Series]:
    valid = pd.Series(True, index=original.index, dtype=bool)
    reasons: dict[object, list[str]] = {index: [] for index in original.index}
    for column in _CRITICAL_ROW_INPUTS.get(str(mineral_key), ()):
        if column not in original.columns:
            valid.loc[:] = False
            for index in original.index:
                reasons[index].append(f"missing column {column}")
            continue
        bad = ~_presence(original, column)
        for index in original.index[bad]:
            reasons[index].append(f"missing/non-finite {column}")
            valid.at[index] = False

    available_fe = [column for column in _FE_COLUMNS if column in original.columns]
    if str(mineral_key) in _FE_REQUIRED_MINERALS and not available_fe:
        valid.loc[:] = False
        for index in original.index:
            reasons[index].append("missing Fe column")
    elif available_fe:
        has_fe = pd.Series(False, index=original.index, dtype=bool)
        for column in available_fe:
            has_fe |= _presence(original, column)
        for index in original.index[~has_fe]:
            reasons[index].append("missing/non-finite Fe")
            valid.at[index] = False
    reason_text = pd.Series(
        ["; ".join(reasons[index]) for index in original.index],
        index=original.index,
        dtype="string",
    )
    return valid, reason_text


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


def _input_provenance(final: pd.DataFrame, original: pd.DataFrame) -> pd.DataFrame:
    out = final.copy()
    recognized = [
        str(column) for column in original.columns
        if str(column) in OXIDES or str(column) in HALOGENS or str(column) in {"FeOt", "Fe2O3t"}
    ]
    out[FORMULA_INPUT_POLICY_COL] = (
        "all recognized measured oxide columns present in the dataset; halogens do not enter oxygen basis"
    )
    out[FORMULA_INPUTS_USED_COL] = ", ".join(recognized)
    return out


def _postprocess_carbonate(final: pd.DataFrame, method_id: str | None) -> pd.DataFrame:
    if "apfu_Fe3" not in final.columns:
        return final
    out = final.copy()
    target = 2.0 if str(method_id) == "carb_2cat" else 1.0
    out["X_Fe3"] = pd.to_numeric(out["apfu_Fe3"], errors="coerce") / target
    return out


def _postprocess_garnet(final: pd.DataFrame) -> pd.DataFrame:
    out = final.copy()
    if "Endmember_sum" in out.columns:
        out["Simplified_endmember_sum"] = out["Endmember_sum"]
    omitted = pd.Series(0.0, index=out.index, dtype=float)
    for cation in _GARNET_OMITTED_Y:
        column = f"apfu_{cation}"
        if column in out.columns:
            omitted += pd.to_numeric(out[column], errors="coerce").fillna(0.0).abs()
    incomplete = omitted > 1e-8
    out["QC_endmember_model"] = np.where(
        incomplete,
        "incomplete: Y-site components omitted from simplified Prp–Alm–Sps–Grs–Adr–Uv model",
        "complete for simplified component set",
    )
    if incomplete.any():
        out.loc[incomplete, SPECIES_COL] = ""
        out.loc[incomplete, FIELD_COL] = "simplified end-member classification withheld"
        out.loc[incomplete, LEVEL_COL] = "incomplete end-member model"
        out.loc[incomplete, NOTE_COL] = (
            "Ti/Zr/Hf/V/Nb/Sn/U-bearing Y-site budget is not represented by the simplified "
            "Prp–Alm–Sps–Grs–Adr–Uv decomposition."
        )
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
    if str(mineral_key) == "carbonate":
        final = _postprocess_carbonate(final, method_id)
    if str(mineral_key) == "garnet":
        final = _postprocess_garnet(final)

    final = _input_provenance(final, dataframe)
    valid, invalid_reason = _critical_row_validity(dataframe, mineral_key)
    protected_status = {
        FORMULA_INPUT_STATUS_COL,
        FORMULA_MISSING_INPUTS_COL,
        FORMULA_INPUT_POLICY_COL,
        FORMULA_INPUTS_USED_COL,
    }
    derived_columns = [
        column for column in final.columns
        if column not in dataframe.columns
        and column not in protected_status
        and not str(column).startswith("_")
    ]
    if derived_columns:
        final.loc[~valid, derived_columns] = np.nan
    final[FORMULA_VALID_COL] = valid
    final[FORMULA_INVALID_REASON_COL] = invalid_reason

    notes = [text for text in (preparation_note, result.note_ru) if text]
    notes.append(
        "Formula input policy: все распознанные измеренные oxide-columns участвуют в базовой катионной/кислородной нормировке; фактически использованные колонки сохраняются в provenance."
    )
    return CalculationResult(final, "\n\n".join(notes))
