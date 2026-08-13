from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd


def install() -> None:
    from petrolab import ternary_presets as target

    preset = target.TERNARY_PRESETS.get("pyroxene_wo_en_fs")
    if preset is not None:
        target.TERNARY_PRESETS["pyroxene_wo_en_fs"] = replace(
            preset,
            mineral_keys=("cpx", "opx", "clinopyroxene", "orthopyroxene"),
        )

    qj_flag = "Morimoto Quad applicable"
    target.MORIMOTO_QJ_APPLICABLE = qj_flag

    def mineral_mask(dataframe: pd.DataFrame, preset) -> pd.Series:
        if not preset.mineral_keys or "Минерал" not in dataframe.columns:
            return pd.Series(True, index=dataframe.index, dtype=bool)
        return dataframe["Минерал"].astype("string").isin(preset.mineral_keys).fillna(False)

    def available(data):
        if isinstance(data, pd.DataFrame):
            columns = set(map(str, data.columns))
            return [
                item for item in target.TERNARY_PRESETS.values()
                if set(item.source_requirements).issubset(columns)
                and bool(mineral_mask(data, item).any())
            ]
        columns = set(map(str, data))
        return [
            item for item in target.TERNARY_PRESETS.values()
            if set(item.source_requirements).issubset(columns)
        ]

    def required(dataframe: pd.DataFrame, column: str) -> pd.Series:
        if column not in dataframe.columns:
            raise ValueError(f"Отсутствует обязательная колонка ternary-проекции: {column}")
        return pd.to_numeric(dataframe[column], errors="coerce")

    def optional(dataframe: pd.DataFrame, column: str) -> pd.Series:
        if column not in dataframe.columns:
            return pd.Series(0.0, index=dataframe.index, dtype=float)
        return pd.to_numeric(dataframe[column], errors="coerce")

    def normalize(dataframe: pd.DataFrame, preset, components):
        if preset.normalization != "normalize":
            return dataframe
        out = dataframe.copy()
        numeric = out[list(components)].apply(pd.to_numeric, errors="coerce")
        total = numeric.sum(axis=1, min_count=len(components))
        valid = total.gt(0) & np.isfinite(total)
        for column in components:
            out[column] = (100.0 * numeric[column] / total).where(valid, np.nan)
        return out

    def apply(dataframe: pd.DataFrame, preset):
        result = dataframe.loc[mineral_mask(dataframe, preset)].copy()
        components = (preset.a_col, preset.b_col, preset.c_col)

        if preset.projection_id == "garnet_ti_grew2013_fig5":
            missing = [column for column in preset.source_requirements if column not in result.columns]
            if missing:
                raise ValueError("Для Ti-гранатовой диаграммы Grew et al. не хватает: " + ", ".join(missing))
            applicable = result["TiGrt_Fig5_applicable"].fillna(False).astype(bool)
            for column in components:
                result[column] = pd.to_numeric(result[column], errors="coerce").where(applicable, np.nan)
            return normalize(result, preset, components), components

        if preset.projection_id != "morimoto_pyroxene_1988":
            return normalize(result, preset, components), components

        missing = [column for column in preset.source_requirements if column not in result.columns]
        if missing:
            raise ValueError("Для IMA-проекции пироксена не хватает: " + ", ".join(missing))

        ca = required(result, "apfu_Ca")
        mg = required(result, "apfu_Mg")
        fe2 = required(result, "apfu_Fe2")
        fe3 = optional(result, "apfu_Fe3")
        mn = optional(result, "apfu_Mn")
        q = required(result, "Q")
        j = required(result, "J")
        sigma_fe = fe2 + fe3 + mn
        total = ca + mg + sigma_fe
        qj = q + j
        with np.errstate(divide="ignore", invalid="ignore"):
            j_fraction = j / qj
        finite = np.isfinite(ca) & np.isfinite(mg) & np.isfinite(fe2) & np.isfinite(fe3) & np.isfinite(mn) & np.isfinite(q) & np.isfinite(j)
        quad = finite & total.gt(0) & qj.between(1.5, 2.0) & j_fraction.le(0.2)
        result[target.MORIMOTO_EN] = (100.0 * mg / total).where(quad, np.nan)
        result[target.MORIMOTO_FS] = (100.0 * sigma_fe / total).where(quad, np.nan)
        result[target.MORIMOTO_WO] = (100.0 * ca / total).where(quad, np.nan)
        result["Morimoto ΣFe"] = sigma_fe.where(quad, np.nan)
        result[qj_flag] = quad
        return result, (target.MORIMOTO_EN, target.MORIMOTO_FS, target.MORIMOTO_WO)

    target.available_ternary_presets = available
    target.apply_preset_projection = apply
