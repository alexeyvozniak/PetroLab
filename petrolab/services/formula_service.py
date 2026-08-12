from __future__ import annotations

import pandas as pd

from petrolab.minerals.classification import (
    FIELD_COL,
    LEVEL_COL,
    METHOD_COL,
    NOTE_COL,
    SPECIES_COL,
    attach_mineral_classification,
)
from petrolab.minerals.formulae import CalculationResult, OXIDES, calculate_formula


FE2O3T_TO_FEOT = (
    2.0 * OXIDES["FeO"].molar_mass / OXIDES["Fe2O3"].molar_mass
)


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


def calculate_formula_safe(
    dataframe: pd.DataFrame,
    mineral_key: str,
    method_id: str | None = None,
) -> CalculationResult:
    """Calculate formula + source-aware classification while hiding temporary conversions."""
    prepared, preparation_note = prepare_formula_input(dataframe)
    result = calculate_formula(prepared, mineral_key, method_id)

    # Present exactly the original source columns plus genuinely calculated fields. Temporary
    # FeOt created from Fe2O3t must never look like a second measured laboratory column.
    final = dataframe.copy()
    for column in result.data.columns:
        if column not in prepared.columns:
            final[column] = result.data[column].to_numpy(copy=False)

    # Classification is interpretation, not the structural-formula calculation itself.
    # Missing classification inputs must therefore degrade to an explicit status instead of
    # destroying a valid formula. Scientific errors in the formula stage still fail hard above.
    try:
        final = attach_mineral_classification(final, mineral_key, method_id)
    except ValueError as exc:
        final = _classification_unavailable(final, exc)

    notes = [text for text in (preparation_note, result.note_ru) if text]
    return CalculationResult(final, "\n\n".join(notes))
