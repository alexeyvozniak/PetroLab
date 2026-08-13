from __future__ import annotations

import pandas as pd

_AW_O = 15.999
_AW_F = 18.998403163
_AW_CL = 35.45


def _numeric_optional(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(float("nan"), index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def add_qc_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Compute transparent EPMA totals without destroying source chemistry.

    F and Cl are measured components, so they enter the raw analytical total.  The
    corresponding oxygen-equivalent correction is then subtracted explicitly.  H2O is
    not added automatically because PetroLab cannot know whether it was measured or
    inferred from stoichiometry.
    """
    from petrolab import io_utils

    out = df.copy()
    numeric = io_utils.numericize_scientific_columns(df)
    duplicate_oxides = io_utils._duplicate_oxide_inputs(out.columns)
    if duplicate_oxides:
        out["QC химии"] = (
            "Конфликтующие химические колонки: " + ", ".join(duplicate_oxides)
        )

    non_fe_oxides = [
        column
        for column in io_utils.oxide_columns(numeric)
        if column not in {"F", "Cl", "H2O", "FeO", "FeOt", "Fe2O3", "Fe2O3t"}
    ]
    base_sum = (
        numeric[non_fe_oxides].sum(axis=1, min_count=1)
        if non_fe_oxides
        else pd.Series(float("nan"), index=out.index, dtype=float)
    )

    feo = _numeric_optional(numeric, "FeO")
    fe2o3 = _numeric_optional(numeric, "Fe2O3")
    feot = _numeric_optional(numeric, "FeOt")
    fe2o3t = _numeric_optional(numeric, "Fe2O3t")
    total_overlap = feot.notna() & fe2o3t.notna()
    total_any = feot.notna() | fe2o3t.notna()
    split_any = feo.notna() | fe2o3.notna()
    iron_conflict = total_overlap | (total_any & split_any)
    if iron_conflict.any():
        out["QC железа"] = "Проверьте: total Fe пересекается с другой формой представления Fe"

    total_reported = feot.combine_first(fe2o3t)
    split_reported = pd.concat([feo, fe2o3], axis=1).sum(axis=1, min_count=1)
    iron_contribution = total_reported.combine_first(split_reported)

    f = _numeric_optional(numeric, "F")
    cl = _numeric_optional(numeric, "Cl")
    halogens = pd.concat([f, cl], axis=1).sum(axis=1, min_count=1)
    raw_total = pd.concat([base_sum, iron_contribution, halogens], axis=1).sum(
        axis=1, min_count=1
    )
    correction = f.fillna(0.0) * _AW_O / (2.0 * _AW_F)
    correction += cl.fillna(0.0) * _AW_O / (2.0 * _AW_CL)
    corrected = raw_total - correction

    if raw_total.notna().any():
        out["Σ компонентов raw"] = raw_total
        out["Поправка O=F,Cl"] = correction
        out["Σ corrected"] = corrected
        # Backwards-compatible display alias. New code should prefer Σ corrected.
        out["Σ оксидов"] = corrected
        invalid_sum = pd.Series(bool(duplicate_oxides), index=out.index) | iron_conflict
        labels = pd.cut(
            corrected,
            bins=[float("-inf"), 97.0, 103.0, float("inf")],
            labels=["низкая", "норма", "высокая"],
            right=True,
        ).astype("string")
        out["QC суммы"] = labels
        out.loc[invalid_sum, "QC суммы"] = "конфликт колонок/железа"
    return out


def install() -> None:
    from petrolab import io_utils

    io_utils.add_qc_columns = add_qc_columns
