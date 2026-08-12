from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class TernaryPreset:
    preset_id: str
    title_ru: str
    mineral_keys: tuple[str, ...]
    a_col: str
    b_col: str
    c_col: str
    a_label: str
    b_label: str
    c_label: str
    normalization: str = "auto"
    description_ru: str = ""
    field_overlay_id: str | None = None
    required_columns: tuple[str, ...] = ()
    projection_id: str | None = None

    @property
    def source_requirements(self) -> tuple[str, ...]:
        return self.required_columns or (self.a_col, self.b_col, self.c_col)


MORIMOTO_EN = "Morimoto En"
MORIMOTO_FS = "Morimoto Fs"
MORIMOTO_WO = "Morimoto Wo"


TERNARY_PRESETS: dict[str, TernaryPreset] = {
    "pyroxene_wo_en_fs": TernaryPreset(
        preset_id="pyroxene_wo_en_fs",
        title_ru="Пироксены · En–Fs–Wo · IMA/Morimoto",
        mineral_keys=("cpx", "opx"),
        a_col=MORIMOTO_EN,
        b_col=MORIMOTO_FS,
        c_col=MORIMOTO_WO,
        a_label="En",
        b_label="Fs",
        c_label="Wo",
        normalization="already",
        description_ru=(
            "Стандартная ориентация: En слева, Fs справа, Wo сверху. Для IMA-проекции "
            "ΣFe = Fe²⁺ + Fe³⁺ + Mn; классификационные поля применяются только к Quad "
            "пироксенам после обязательной Q–J проверки."
        ),
        field_overlay_id="pyroxene_morimoto_1988",
        required_columns=("apfu_Ca", "apfu_Mg", "apfu_Fe2", "Q", "J"),
        projection_id="morimoto_pyroxene_1988",
    ),
    "feldspar_ab_an_or": TernaryPreset(
        preset_id="feldspar_ab_an_or",
        title_ru="Полевые шпаты · Ab–An–Or",
        mineral_keys=("feldspar",),
        a_col="Ab",
        b_col="An",
        c_col="Or",
        a_label="Ab",
        b_label="An",
        c_label="Or",
        normalization="auto",
        description_ru=(
            "Ab слева, An справа, Or сверху. Сам Ab–An–Or состав строится напрямую. "
            "Литературные границы полей пока не накладываются автоматически: текст источника "
            "подтверждает схему Deer et al. (1992), но точная геометрия полей дана на рисунке "
            "и не заменяется эвристическим порогом Or."
        ),
        field_overlay_id=None,
    ),
    "garnet_prp_alm_grs": TernaryPreset(
        preset_id="garnet_prp_alm_grs",
        title_ru="Гранаты · Prp–Alm–Grs",
        mineral_keys=("garnet",),
        a_col="Prp",
        b_col="Alm",
        c_col="Grs",
        a_label="Prp",
        b_label="Alm",
        c_label="Grs",
        normalization="normalize",
        description_ru=(
            "Проекция Prp–Alm–Grs по сохранённым end-member компонентам. Остальные компоненты "
            "граната исключаются из этой трёхкомпонентной проекции нормировкой."
        ),
    ),
    "garnet_prp_alm_sps": TernaryPreset(
        preset_id="garnet_prp_alm_sps",
        title_ru="Гранаты · Prp–Alm–Sps",
        mineral_keys=("garnet",),
        a_col="Prp",
        b_col="Alm",
        c_col="Sps",
        a_label="Prp",
        b_label="Alm",
        c_label="Sps",
        normalization="normalize",
        description_ru=(
            "Проекция Prp–Alm–Sps по сохранённым end-member компонентам; компоненты Ca и Cr/Fe³⁺ "
            "не входят в эту конкретную трёхкомпонентную проекцию."
        ),
    ),
}


def available_ternary_presets(columns: list[str] | tuple[str, ...] | set[str]) -> list[TernaryPreset]:
    available = set(map(str, columns))
    return [
        preset
        for preset in TERNARY_PRESETS.values()
        if set(preset.source_requirements).issubset(available)
    ]


def _numeric_or_zero(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(0.0, index=dataframe.index, dtype=float)
    return pd.to_numeric(dataframe[column], errors="coerce").fillna(0.0)


def apply_preset_projection(
    dataframe: pd.DataFrame,
    preset: TernaryPreset,
) -> tuple[pd.DataFrame, tuple[str, str, str]]:
    """Return a view with any source-specific ternary projection columns added.

    This never edits persisted analytical or formula data. Source-specific projections are
    view-only fields used by the selected diagram and its export.
    """
    result = dataframe.copy()
    if preset.projection_id != "morimoto_pyroxene_1988":
        return result, (preset.a_col, preset.b_col, preset.c_col)

    missing = [column for column in preset.source_requirements if column not in result.columns]
    if missing:
        raise ValueError("Для IMA-проекции пироксена не хватает: " + ", ".join(missing))

    ca = _numeric_or_zero(result, "apfu_Ca")
    mg = _numeric_or_zero(result, "apfu_Mg")
    fe2 = _numeric_or_zero(result, "apfu_Fe2")
    fe3 = _numeric_or_zero(result, "apfu_Fe3")
    mn = _numeric_or_zero(result, "apfu_Mn")
    sigma_fe = fe2 + fe3 + mn
    total = ca + mg + sigma_fe
    valid = total > 0

    result[MORIMOTO_EN] = np.where(valid, 100.0 * mg / total, np.nan)
    result[MORIMOTO_FS] = np.where(valid, 100.0 * sigma_fe / total, np.nan)
    result[MORIMOTO_WO] = np.where(valid, 100.0 * ca / total, np.nan)
    result["Morimoto ΣFe"] = sigma_fe
    return result, (MORIMOTO_EN, MORIMOTO_FS, MORIMOTO_WO)
