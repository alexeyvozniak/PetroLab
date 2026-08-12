from __future__ import annotations

from dataclasses import dataclass


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


TERNARY_PRESETS: dict[str, TernaryPreset] = {
    "pyroxene_wo_en_fs": TernaryPreset(
        preset_id="pyroxene_wo_en_fs",
        title_ru="Пироксены · Wo–En–Fs",
        mineral_keys=("cpx", "opx"),
        a_col="Wo",
        b_col="En",
        c_col="Fs",
        a_label="Wo",
        b_label="En",
        c_label="Fs",
        normalization="auto",
        description_ru=(
            "Треугольник конечных компонентов пироксена по рассчитанным Wo–En–Fs. "
            "Поля классификации будут подключаться отдельным проверяемым overlay, "
            "чтобы границы не задавались приблизительно."
        ),
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
            "Треугольник Ab–An–Or по рассчитанным конечным компонентам полевого шпата. "
            "Литературные классификационные границы не рисуются без явного источника/набора координат."
        ),
    ),
}


def available_ternary_presets(columns: list[str] | tuple[str, ...] | set[str]) -> list[TernaryPreset]:
    available = set(map(str, columns))
    return [
        preset
        for preset in TERNARY_PRESETS.values()
        if {preset.a_col, preset.b_col, preset.c_col}.issubset(available)
    ]
