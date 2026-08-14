from __future__ import annotations

import numpy as np
import pandas as pd


TAS_NON_FE_MAJOR_OXIDES: tuple[str, ...] = (
    "SiO2", "TiO2", "Al2O3", "Cr2O3", "MnO", "MgO", "CaO",
    "Na2O", "K2O", "P2O5", "NiO", "BaO", "SrO",
)
TAS_REQUIRED_MAJOR_COMPONENTS: tuple[str, ...] = (
    "SiO2", "Al2O3", "MgO", "CaO", "Na2O", "K2O",
)
TAS_MIN_PLAUSIBLE_MAJOR_TOTAL = 70.0
TAS_MAX_PLAUSIBLE_MAJOR_TOTAL = 105.0


def _numeric(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(np.nan, index=dataframe.index, dtype=float)
    return pd.to_numeric(dataframe[column], errors="coerce")


def _iron_mass_for_total(dataframe: pd.DataFrame) -> pd.Series:
    """Choose one mutually exclusive reported iron representation for the major total."""
    feot = _numeric(dataframe, "FeOt")
    fe2o3t = _numeric(dataframe, "Fe2O3t")
    feo = _numeric(dataframe, "FeO")
    fe2o3 = _numeric(dataframe, "Fe2O3")
    split = feo.add(fe2o3, fill_value=0.0)
    split = split.where(feo.notna() | fe2o3.notna())
    return feot.combine_first(fe2o3t).combine_first(split)


def tas_major_total(dataframe: pd.DataFrame) -> pd.Series:
    total = pd.Series(0.0, index=dataframe.index, dtype=float)
    any_major = pd.Series(False, index=dataframe.index)
    for oxide in TAS_NON_FE_MAJOR_OXIDES:
        values = _numeric(dataframe, oxide)
        total = total.add(values.fillna(0.0), fill_value=0.0)
        any_major = any_major | values.notna()
    iron = _iron_mass_for_total(dataframe)
    total = total.add(iron.fillna(0.0), fill_value=0.0)
    any_major = any_major | iron.notna()
    return total.where(any_major)


def tas_normalization_qc(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Return per-row evidence that volatile-free TAS renormalization is defensible.

    TAS is not allowed to inflate a fragmentary table (for example SiO2+Na2O+K2O only)
    to 100 %. A compact essential major suite, an iron measurement/total and a plausible
    pre-normalization major total are required. The limits are QC gates, not rock-class
    boundaries.
    """
    total = tas_major_total(dataframe)
    required_ok = pd.Series(True, index=dataframe.index)
    missing_lists: list[list[str]] = [[] for _ in range(len(dataframe))]
    index_positions = {index: pos for pos, index in enumerate(dataframe.index)}
    for oxide in TAS_REQUIRED_MAJOR_COMPONENTS:
        values = _numeric(dataframe, oxide)
        present = values.notna()
        required_ok = required_ok & present
        for index in dataframe.index[~present]:
            missing_lists[index_positions[index]].append(oxide)
    iron = _iron_mass_for_total(dataframe)
    iron_ok = iron.notna()
    for index in dataframe.index[~iron_ok]:
        missing_lists[index_positions[index]].append("Fe(total or split)")

    plausible_total = total.between(TAS_MIN_PLAUSIBLE_MAJOR_TOTAL, TAS_MAX_PLAUSIBLE_MAJOR_TOTAL, inclusive="both")
    complete = required_ok & iron_ok & plausible_total
    messages: list[str] = []
    for pos, index in enumerate(dataframe.index):
        reasons: list[str] = []
        if missing_lists[pos]:
            reasons.append("missing: " + ", ".join(missing_lists[pos]))
        value = total.loc[index]
        if pd.isna(value):
            reasons.append("major total unavailable")
        elif not plausible_total.loc[index]:
            reasons.append(
                f"major total {float(value):.2f} wt.% outside QC range "
                f"{TAS_MIN_PLAUSIBLE_MAJOR_TOTAL:g}–{TAS_MAX_PLAUSIBLE_MAJOR_TOTAL:g}"
            )
        messages.append("OK" if not reasons else "; ".join(reasons))
    return pd.DataFrame(
        {
            "TAS_major_suite_complete": complete.astype(bool),
            "TAS_normalization_QC": messages,
            "TAS_original_major_total": total,
        },
        index=dataframe.index,
    )


def prepare_tas_dataframe(dataframe: pd.DataFrame, *, normalize_volatile_free: bool = True) -> pd.DataFrame:
    """Prepare TAS coordinates without mutating stored whole-rock chemistry."""
    work = dataframe.copy()
    sio2 = _numeric(work, "SiO2")
    na2o = _numeric(work, "Na2O")
    k2o = _numeric(work, "K2O")
    qc = tas_normalization_qc(work)
    total = qc["TAS_original_major_total"]

    if normalize_volatile_free:
        factor = 100.0 / total.where(qc["TAS_major_suite_complete"] & (total > 0))
    else:
        factor = pd.Series(1.0, index=work.index, dtype=float)

    work["TAS_original_major_total"] = total
    work["TAS_major_suite_complete"] = qc["TAS_major_suite_complete"]
    work["TAS_normalization_QC"] = qc["TAS_normalization_QC"]
    work["TAS_normalization_factor"] = factor
    work["TAS_SiO2"] = sio2 * factor
    work["TAS_Total_alkalis"] = (na2o + k2o) * factor
    work["TAS_normalized_volatile_free"] = bool(normalize_volatile_free)
    return work
