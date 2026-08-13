from __future__ import annotations

import numpy as np
import pandas as pd

from petrolab.minerals.classification import (
    FIELD_COL,
    LEVEL_COL,
    METHOD_COL,
    NOTE_COL,
    SPECIES_COL,
    attach_mineral_classification,
)
from petrolab.minerals.formulae import CalculationResult, HALOGENS, OXIDES, calculate_formula
from petrolab.minerals.garnet_ti import apply_strict_grew_figure5
from petrolab.minerals.registry import MINERALS


FE2O3T_TO_FEOT = (
    2.0 * OXIDES["FeO"].molar_mass / OXIDES["Fe2O3"].molar_mass
)

FORMULA_INPUT_STATUS_COL = "QC formula input"
FORMULA_MISSING_INPUTS_COL = "Formula missing inputs"


def prepare_formula_input(dataframe: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Prepare reporting-basis iron columns for a structural-formula calculation."""
    work = dataframe.copy()
    if "Fe2O3t" not in work.columns:
        return work, ""

    total_fe2o3 = pd.to_numeric(work["Fe2O3t"], errors="coerce")
    present = total_fe2o3.notna()
    if not present.any():
        return work.drop(columns=["Fe2O3t"]), ""

    conflicts: list[str] = []
    for column in ("FeO", "FeOt", "Fe2O3"):
        if column not in work.columns:
            continue
        other = pd.to_numeric(work[column], errors="coerce")
        if (present & other.notna()).any():
            conflicts.append(column)
    if conflicts:
        raise ValueError(
            "Fe2O3t (ΣFe как Fe2O3) одновременно задан с "
            + ", ".join(conflicts)
            + " в одной или нескольких строках. Нельзя определить источник total Fe однозначно."
        )

    converted = total_fe2o3 * FE2O3T_TO_FEOT
    if "FeOt" in work.columns:
        feot = pd.to_numeric(work["FeOt"], errors="coerce")
        work["FeOt"] = feot.combine_first(converted)
    else:
        work["FeOt"] = converted
    work = work.drop(columns=["Fe2O3t"])
    note = (
        "Fe2O3t интерпретирован как ΣFe, выраженное на базе Fe2O3, и перед расчётом "
        f"переведён в FeOt с коэффициентом {FE2O3T_TO_FEOT:.8f}. "
        "Это преобразование меняет только форму отчётности total Fe, а не задаёт Fe³⁺/Fe²⁺."
    )
    return work, note


def _classification_unavailable(dataframe: pd.DataFrame, error: ValueError) -> pd.DataFrame:
    """Return explicit interpretation status without hiding a valid structural formula."""
    result = dataframe.copy()
    result[SPECIES_COL] = ""
    result[FIELD_COL] = "Автоматическая классификация недоступна для этих входных данных"
    result[LEVEL_COL] = "insufficient classification inputs"
    result[METHOD_COL] = ""
    result[NOTE_COL] = str(error)
    return result


def _numeric_presence(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(False, index=dataframe.index, dtype=bool)
    return pd.to_numeric(dataframe[column], errors="coerce").notna()


def _supplied_formula_columns(dataframe: pd.DataFrame, mineral_key: str) -> list[str]:
    module = MINERALS.get(str(mineral_key))
    typical = tuple(module.typical_oxides) if module is not None else tuple(OXIDES) + tuple(HALOGENS)
    supplied = [column for column in typical if column in dataframe.columns]
    if "FeO" in typical:
        for column in ("FeOt", "Fe2O3t"):
            if column in dataframe.columns and column not in supplied:
                supplied.append(column)
    return supplied


def _restore_missing_input_semantics(
    result: pd.DataFrame,
    original: pd.DataFrame,
    mineral_key: str,
) -> pd.DataFrame:
    """Keep a blank analytical cell distinct from a measured chemical zero.

    The low-level normalizer necessarily uses zero contribution for an unavailable
    oxide while summing the chemistry that is present. At the public result layer we
    restore the analytical semantics: if a source column exists but a particular row
    is blank/non-numeric, the corresponding apfu value is NaN rather than 0 and an
    explicit row-level QC message records the partial analytical panel.
    """
    out = result.copy()
    supplied = _supplied_formula_columns(original, mineral_key)

    missing_by_row: dict[object, list[str]] = {index: [] for index in original.index}
    for column in supplied:
        present = _numeric_presence(original, column)
        for index in original.index[~present]:
            missing_by_row[index].append(column)

    # Most oxides map one-to-one to one cation output. Preserve NaN for a missing
    # cell even though the internal normalization treated that unavailable component
    # as contributing zero mass to the row sum.
    for oxide, spec in OXIDES.items():
        output_column = f"apfu_{spec.cation}"
        if oxide not in original.columns or output_column not in out.columns:
            continue
        missing = ~_numeric_presence(original, oxide)
        out.loc[missing, output_column] = np.nan

    # FeO and FeOt are alternative reporting bases for Fe2 in the formula engine.
    # Only mark apfu_Fe2 unknown when none of the row-level total/ferrous Fe sources
    # contains a numeric value.
    fe_sources = [column for column in ("FeO", "FeOt", "Fe2O3t") if column in original.columns]
    if fe_sources and "apfu_Fe2" in out.columns:
        fe_present = pd.Series(False, index=original.index, dtype=bool)
        for column in fe_sources:
            fe_present = fe_present | _numeric_presence(original, column)
        out.loc[~fe_present, "apfu_Fe2"] = np.nan

    for halogen in HALOGENS:
        output_column = f"apfu_{halogen}"
        if halogen not in original.columns or output_column not in out.columns:
            continue
        missing = ~_numeric_presence(original, halogen)
        out.loc[missing, output_column] = np.nan

    # OH estimates are directly dependent on halogen occupancy. A blank F or Cl cell
    # in an otherwise supplied column is unknown, not zero. If the column is absent
    # altogether, legacy behaviour is retained because that is an explicit reduced
    # analytical panel rather than a row-level hole in a supplied panel.
    halogen_hole = pd.Series(False, index=original.index, dtype=bool)
    for halogen in ("F", "Cl"):
        if halogen in original.columns:
            halogen_hole = halogen_hole | ~_numeric_presence(original, halogen)
    if halogen_hole.any():
        for dependent in ("apfu_OH_max", "apfu_OH_est"):
            if dependent in out.columns:
                out.loc[halogen_hole, dependent] = np.nan
        if "QC_Z_site" in out.columns:
            out.loc[halogen_hole, "QC_Z_site"] = "не рассчитано: пропуск F/Cl"

    missing_text = pd.Series("", index=original.index, dtype="string")
    status = pd.Series("полный набор в представленных колонках", index=original.index, dtype="string")
    for index, columns in missing_by_row.items():
        if columns:
            missing_text.at[index] = ", ".join(columns)
            status.at[index] = "частичный аналитический набор: есть пропуски в строке"
    out[FORMULA_INPUT_STATUS_COL] = status
    out[FORMULA_MISSING_INPUTS_COL] = missing_text
    return out


def calculate_formula_safe(
    dataframe: pd.DataFrame,
    mineral_key: str,
    method_id: str | None = None,
) -> CalculationResult:
    """Calculate formula + source-aware classification while hiding temporary conversions."""
    prepared, preparation_note = prepare_formula_input(dataframe)
    result = calculate_formula(prepared, mineral_key, method_id)

    final = dataframe.copy()
    for column in result.data.columns:
        if column not in prepared.columns:
            final[column] = result.data[column].to_numpy(copy=False)

    final = _restore_missing_input_semantics(final, dataframe, mineral_key)

    try:
        final = attach_mineral_classification(final, mineral_key, method_id)
        if str(mineral_key) == "garnet":
            final = apply_strict_grew_figure5(final)
    except ValueError as exc:
        final = _classification_unavailable(final, exc)

    notes = [text for text in (preparation_note, result.note_ru) if text]
    return CalculationResult(final, "\n\n".join(notes))
