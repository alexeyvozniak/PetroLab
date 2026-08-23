from __future__ import annotations

import pandas as pd

from . import formulae as _formulae
from .input_validation import SCIENTIFIC_FORMULA_COLUMNS, validate_formula_inputs


# Capture every registered calculator before installing wrappers. Common input validation
# is therefore a single invariant for all mineral methods, while the Fe/mica policies below
# only alter the specific methods that need them.
_ORIGINAL_CALCULATORS = dict(_formulae.CALCULATORS)

_ALL_FE2_METHODS = {
    "ol_4o_fe2",
    "px_6o_fe2",
    "grt_12o_fe2",
    "mica_rieder_11o",
    "mica_rieder_22o",
    "sp_4o_fe2",
    "ilm_3o_fe2",
}

_FE2O3_TO_FEO_EQUIVALENT = (
    2.0 * _formulae.OXIDES["FeO"].molar_mass
    / _formulae.OXIDES["Fe2O3"].molar_mass
)


def _floor_negative_formula_inputs(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    """Floor physically impossible negative concentrations only in a calculation copy."""
    work = df.copy()
    changed: dict[str, int] = {}
    for column in work.columns:
        name = str(column)
        if name not in SCIENTIFIC_FORMULA_COLUMNS:
            continue
        values = pd.to_numeric(work[column], errors="coerce")
        negative = values.lt(0).fillna(False)
        count = int(negative.sum())
        if not count:
            continue
        work.loc[negative, column] = 0.0
        changed[name] = count
    return work, changed


def _prepare_all_fe_as_fe2(df: pd.DataFrame) -> tuple[pd.DataFrame, bool]:
    """Convert separately reported Fe2O3 to an FeO-equivalent total for explicit Fe2 methods.

    Selecting an ``*_fe2`` method is itself an explicit scientific assumption that all iron
    is treated as ferrous for the structural formula. When FeO and Fe2O3 were reported
    separately, atom balance is preserved by converting ferric oxide to its FeO-equivalent
    and adding it to FeO. FeOt already denotes total Fe, so FeOt + Fe2O3 remains ambiguous
    and is rejected rather than double-counted.
    """
    if "Fe2O3" not in df.columns:
        return df, False

    fe3 = pd.to_numeric(df["Fe2O3"], errors="coerce")
    if not fe3.notna().any():
        return df, False

    if "FeOt" in df.columns:
        feot = pd.to_numeric(df["FeOt"], errors="coerce")
        conflict = feot.notna() & fe3.notna()
        if conflict.any():
            raise ValueError(
                "Метод «весь Fe как Fe²⁺» не может объединить FeOt и отдельно заданный Fe2O3: "
                "FeOt уже содержит total Fe. Сначала выберите один однозначный источник total Fe."
            )

    work = df.copy()
    fe3_as_feo = fe3 * _FE2O3_TO_FEO_EQUIVALENT
    if "FeO" in work.columns:
        feo = pd.to_numeric(work["FeO"], errors="coerce")
        combined = feo.fillna(0.0) + fe3_as_feo.fillna(0.0)
        combined = combined.mask(feo.isna() & fe3.isna())
        work["FeO"] = combined
    else:
        work["FeO"] = fe3_as_feo
    work = work.drop(columns=["Fe2O3"])
    return work, True


def _restore_source_columns(
    source: pd.DataFrame,
    working: pd.DataFrame,
    calculated: pd.DataFrame,
) -> pd.DataFrame:
    """Return original source columns plus only fields derived by the calculator."""
    out = source.copy()
    for column in calculated.columns:
        if column not in working.columns:
            out[column] = calculated[column]
    return out


def _run_policy_calculator(
    mineral_key: str,
    df: pd.DataFrame,
    method_id: str,
) -> _formulae.CalculationResult:
    original = _ORIGINAL_CALCULATORS[mineral_key]
    validate_formula_inputs(df)
    work, floored = _floor_negative_formula_inputs(df)
    temporary_halogen_columns: list[str] = []

    # The mica routine can estimate an OH maximum when an entire halogen panel was not
    # measured. Row-level holes inside a supplied F/Cl column are handled elsewhere and
    # must not be converted to zeros here.
    if mineral_key == "mica":
        for name in ("F", "Cl"):
            if name not in work.columns:
                work[name] = pd.Series(0.0, index=work.index, dtype=float)
                temporary_halogen_columns.append(name)

    converted_fe = False
    if method_id in _ALL_FE2_METHODS:
        work, converted_fe = _prepare_all_fe_as_fe2(work)

    result = original(work, method_id)
    restored = _restore_source_columns(df, work, result.data)

    notes = [result.note_ru] if result.note_ru else []
    if floored:
        summary = ", ".join(f"{name}: {count}" for name, count in sorted(floored.items()))
        notes.append(
            "Отрицательные аналитические концентрации были приняты равными 0 только для расчёта "
            f"({summary}). Исходные значения сохранены без изменения."
        )
    if converted_fe:
        notes.append(
            "Для выбранного режима «весь Fe как Fe²⁺» отдельно заданный Fe2O3 был "
            f"пересчитан на FeO-equivalent (×{_FE2O3_TO_FEO_EQUIVALENT:.8f}) и объединён "
            "с FeO только для расчёта; исходные колонки сохранены без изменения."
        )
    if temporary_halogen_columns:
        notes.append(
            "Отсутствующие во всём наборе F/Cl приняты равными нулю только для "
            "стехиометрического OH_max; исходная схема колонок не изменена."
        )
    return _formulae.CalculationResult(restored, "\n\n".join(notes))


def install_runtime_fixes() -> None:
    for mineral_key in _ORIGINAL_CALCULATORS:
        _formulae.CALCULATORS[mineral_key] = (
            lambda df, method_id, key=mineral_key: _run_policy_calculator(key, df, method_id)
        )
