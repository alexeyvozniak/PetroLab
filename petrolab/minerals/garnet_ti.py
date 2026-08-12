from __future__ import annotations

import numpy as np
import pandas as pd


def _numeric(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(0.0, index=dataframe.index, dtype=float)
    return pd.to_numeric(dataframe[column], errors="coerce").fillna(0.0)


def apply_strict_grew_figure5(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Recalculate Grew et al. (2013) Fig. 5 components using Y(Ti + Zr) literally.

    The site-allocation layer may track other tetravalent Y-site cations (e.g. Hf) for QC,
    but the published Figure-5 diagnostic explicitly uses Ti + Zr. Those other cations must
    therefore not move the Schorlomite–Morimotoite–Andradite plot coordinates.
    """
    result = dataframe.copy()
    required = {"grt_Y_Ti", "grt_Z_Al", "grt_Z_Fe3", "grt_Y_Al", "grt_Y_Fe3"}
    if not required.issubset(result.columns):
        return result

    y_ti = _numeric(result, "grt_Y_Ti")
    y_zr = _numeric(result, "grt_Y_Zr")
    y_hf = _numeric(result, "grt_Y_Hf")
    y_tizr = y_ti + y_zr
    y_r4_total = y_tizr + y_hf

    z_r3 = _numeric(result, "grt_Z_Al") + _numeric(result, "grt_Z_Fe3")
    y_r3 = (
        _numeric(result, "grt_Y_Al")
        + _numeric(result, "grt_Y_Fe3")
        + _numeric(result, "grt_Y_Cr")
        + _numeric(result, "grt_Y_V3")
        + _numeric(result, "grt_Y_Mn3")
    )
    y_r2 = _numeric(result, "grt_Y_Mg") + _numeric(result, "grt_Y_Fe2") + _numeric(result, "grt_Y_Mn")

    sch_raw = np.minimum(y_tizr, z_r3)
    mor_raw = np.maximum(y_tizr - sch_raw, 0.0)
    adr_raw = y_r3
    total = sch_raw + mor_raw + adr_raw
    valid = total > 0

    result["TiGrt_Sch"] = np.where(valid, 100.0 * sch_raw / total, np.nan)
    result["TiGrt_Mor"] = np.where(valid, 100.0 * mor_raw / total, np.nan)
    result["TiGrt_Adr"] = np.where(valid, 100.0 * adr_raw / total, np.nan)
    result["TiGrt_Y_TiZr"] = y_tizr
    result["TiGrt_Y_R4"] = y_tizr
    result["TiGrt_Y_R4_total_including_Hf"] = y_r4_total
    result["TiGrt_Z_R3"] = z_r3
    result["TiGrt_Y_R3"] = y_r3
    result["TiGrt_Y_R2"] = y_r2

    fields: list[str] = []
    mg_flags: list[bool] = []
    for index in result.index:
        values = {
            "Schorlomite": result.at[index, "TiGrt_Sch"],
            "Morimotoite": result.at[index, "TiGrt_Mor"],
            "Andradite": result.at[index, "TiGrt_Adr"],
        }
        finite = {name: float(value) for name, value in values.items() if pd.notna(value) and np.isfinite(float(value))}
        dominant = max(finite, key=finite.get) if finite else ""
        fields.append(dominant)
        applicable = bool(result.at[index, "TiGrt_Fig5_applicable"]) if "TiGrt_Fig5_applicable" in result else False
        mg_flags.append(
            applicable
            and dominant == "Morimotoite"
            and float(_numeric(result, "grt_Y_Mg").loc[index]) > float(_numeric(result, "grt_Y_Fe2").loc[index])
        )
    result["TiGrt_field"] = fields
    result["TiGrt_Mg_morimotoite_analog_flag"] = mg_flags

    if "grt_site_QC" in result.columns:
        hf_material = y_hf > 0.05
        for index in result.index[hf_material]:
            old = str(result.at[index, "grt_site_QC"] or "").strip()
            message = "Hf tracked in Y-site QC but excluded from Grew Fig. 5 Ti+Zr coordinates"
            if message not in old:
                result.at[index, "grt_site_QC"] = f"{old}; {message}".strip("; ")
    return result
