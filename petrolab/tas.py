from __future__ import annotations

import numpy as np
import pandas as pd


# Major oxides used to reconstruct an anhydrous/volatile-free analytical total before
# plotting TAS. Volatile species (H2O, CO2, LOI, F, Cl, S reported separately, etc.) are
# intentionally excluded. Iron is handled separately so total-Fe and split Fe columns are
# never counted twice.
TAS_NON_FE_MAJOR_OXIDES: tuple[str, ...] = (
    "SiO2", "TiO2", "Al2O3", "Cr2O3", "MnO", "MgO", "CaO",
    "Na2O", "K2O", "P2O5", "NiO", "BaO", "SrO",
)


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

    # Prefer explicit total-iron reporting. If it is absent, use the split measured oxides.
    # The values remain in their reported oxide mass basis because TAS renormalization needs
    # the analytical mass total, not a redox conversion.
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


def prepare_tas_dataframe(dataframe: pd.DataFrame, *, normalize_volatile_free: bool = True) -> pd.DataFrame:
    """Prepare TAS coordinates without mutating stored whole-rock chemistry.

    In IUGS-classification mode, available non-volatile major oxides are renormalized to
    100 wt.%. This is intentionally a plotting/classification transform only; raw chemistry
    remains unchanged and the original analytical total is retained for QC/provenance.
    """
    work = dataframe.copy()
    sio2 = _numeric(work, "SiO2")
    na2o = _numeric(work, "Na2O")
    k2o = _numeric(work, "K2O")
    total = tas_major_total(work)

    if normalize_volatile_free:
        factor = 100.0 / total.where(total > 0)
    else:
        factor = pd.Series(1.0, index=work.index, dtype=float)

    work["TAS_original_major_total"] = total
    work["TAS_normalization_factor"] = factor
    work["TAS_SiO2"] = sio2 * factor
    work["TAS_Total_alkalis"] = (na2o + k2o) * factor
    work["TAS_normalized_volatile_free"] = bool(normalize_volatile_free)
    return work
