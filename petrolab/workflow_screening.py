from __future__ import annotations

import math

import pandas as pd


OUTLIER_COLUMN = "Potential chemical outlier"
OUTLIER_REASON_COLUMN = "Chemical outlier reason"

# Screening only: these are measured major/minor components normally reported in wt.%.
# The routine is deliberately not used for trace-element ppm columns or derived values.
_SCREEN_COLUMNS = (
    "SiO2", "TiO2", "Al2O3", "Cr2O3", "MnO", "MgO", "CaO", "Na2O", "K2O",
    "P2O5", "Nb2O5", "Ta2O5", "ZrO2", "SrO", "BaO", "F", "Cl",
)


def _chemistry_columns(dataframe: pd.DataFrame) -> list[str]:
    columns = [column for column in _SCREEN_COLUMNS if column in dataframe.columns]
    # Do not count multiple total-Fe representations as independent evidence. Prefer the
    # explicit total-as-FeO form, then measured FeO. A separately measured Fe2O3 may still
    # be useful as its own variable when present.
    if "FeOt" in dataframe.columns:
        columns.append("FeOt")
    elif "FeO" in dataframe.columns:
        columns.append("FeO")
    if "Fe2O3" in dataframe.columns and "Fe2O3t" not in dataframe.columns:
        columns.append("Fe2O3")
    elif "Fe2O3t" in dataframe.columns and "FeOt" not in dataframe.columns:
        columns.append("Fe2O3t")
    return columns


def attach_chemical_outlier_screen(
    dataframe: pd.DataFrame,
    *,
    group_column: str | None = None,
    min_group_size: int = 8,
    robust_z_limit: float = 6.0,
) -> pd.DataFrame:
    """Attach a conservative, non-destructive within-group chemistry screening flag.

    This is intentionally an exploratory screen, not an exclusion rule. For each sufficiently
    populated recognition group, each measured wt.% component is compared with the group median
    using a robust MAD/IQR scale. Rows are flagged only for large deviations. Small groups and
    zero-dispersion components are left unclassified rather than forcing an outlier decision.

    No row is removed and no QC decision is changed. The caller should present the result as
    "potential chemical outlier" and leave the final interpretation to the user.
    """
    out = dataframe.copy()
    out[OUTLIER_COLUMN] = False
    out[OUTLIER_REASON_COLUMN] = ""
    if out.empty:
        return out

    chemistry = _chemistry_columns(out)
    if not chemistry:
        return out

    if group_column and group_column in out.columns:
        groups = out[group_column].fillna("").astype(str).str.strip().replace("", "__unresolved__")
    else:
        groups = pd.Series("__all__", index=out.index, dtype="object")

    reasons: dict[object, list[str]] = {index: [] for index in out.index}
    for group_name in groups.unique():
        group_index = groups.index[groups == group_name]
        if len(group_index) < int(min_group_size):
            continue
        for column in chemistry:
            values = pd.to_numeric(out.loc[group_index, column], errors="coerce")
            valid = values.dropna()
            if len(valid) < max(6, int(min_group_size * 0.7)):
                continue
            median = float(valid.median())
            absolute = (valid - median).abs()
            mad = float(absolute.median())
            q1 = float(valid.quantile(0.25))
            q3 = float(valid.quantile(0.75))
            iqr_scale = (q3 - q1) / 1.349 if q3 > q1 else 0.0
            scale = max(1.4826 * mad, iqr_scale, 0.15)
            if not math.isfinite(scale) or scale <= 0:
                continue
            z = absolute / scale
            # Require both a large robust deviation and a visible absolute shift. This avoids
            # calling tiny analytical scatter around ~0 wt.% an "outlier" merely because MAD is
            # numerically very small.
            flagged = z[(z >= float(robust_z_limit)) & (absolute >= 0.5)]
            for index in flagged.index:
                value = float(valid.loc[index])
                reasons[index].append(f"{column}: {value:g} wt.% против медианы {median:g}")

    for index, row_reasons in reasons.items():
        if row_reasons:
            out.at[index, OUTLIER_COLUMN] = True
            out.at[index, OUTLIER_REASON_COLUMN] = "; ".join(row_reasons[:4])
    return out
