from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class PlotRecommendation:
    title: str
    route: str
    x: str = ""
    y: str = ""
    note: str = ""


# These are starting views, not new scientific classifications. A recommendation
# is returned only when every requested column is actually present in the data.
_XY_CANDIDATES: dict[str, tuple[tuple[str, str, str, str], ...]] = {
    "mica": (
        ("Al₂O₃–TiO₂", "Al2O3", "TiO2", "Быстрый обзор эволюции и групп слюд."),
        ("Mg#–TiO₂", "Mg#_formula", "TiO2", "После APFU: Mg# против TiO₂."),
        ("Al₂O₃–FeO", "Al2O3", "FeO", "Удобно сравнивать группы и зональность."),
    ),
    "clinopyroxene": (
        ("Na₂O–Cr₂O₃", "Na2O", "Cr2O3", "Быстрый обзор Na- и Cr-вариаций."),
        ("Mg#–TiO₂", "Mg#_formula", "TiO2", "После APFU: магнезиальность и Ti."),
        ("CaO–Na₂O", "CaO", "Na2O", "Простой первый обзор клинопироксенов."),
    ),
    "orthopyroxene": (
        ("Mg#–Al₂O₃", "Mg#_formula", "Al2O3", "После APFU: магнезиальность и Al."),
        ("MgO–FeO", "MgO", "FeO", "Быстрый обзор Mg–Fe вариации."),
    ),
    "garnet": (
        ("CaO–Cr₂O₃", "CaO", "Cr2O3", "Полезный первый обзор гранатов."),
        ("Prp–Grs", "Prp", "Grs", "После структурного пересчёта."),
        ("Mg#–TiO₂", "Mg#_formula", "TiO2", "После APFU: Mg# и Ti."),
    ),
    "olivine": (
        ("Fo–NiO", "Fo", "NiO", "Если Ni задан как NiO."),
        ("Fo–Ni", "Fo", "Ni", "Если Ni задан как элемент."),
        ("MgO–FeO", "MgO", "FeO", "Работает ещё до расчёта Fo."),
    ),
    "feldspar": (
        ("An–Or", "An", "Or", "После расчёта An–Ab–Or."),
        ("Na₂O–K₂O", "Na2O", "K2O", "Быстрый обзор до структурного пересчёта."),
    ),
    "spinel": (
        ("Cr#–Mg#", "Cr#", "Mg#_formula", "После APFU: классический обзор шпинелей."),
        ("TiO₂–Cr₂O₃", "TiO2", "Cr2O3", "Доступен прямо из оксидов."),
    ),
    "fe_ti_oxide": (
        ("MgO–TiO₂", "MgO", "TiO2", "Первый обзор ильменитовых/Fe–Ti оксидов."),
        ("MnO–TiO₂", "MnO", "TiO2", "Полезно для эволюции Fe–Ti оксидов."),
    ),
    "apatite": (
        ("F–Cl", "F", "Cl", "Если оба галогена измерены."),
        ("SrO–MnO", "SrO", "MnO", "Простой обзор вариаций апатита."),
    ),
    "perovskite": (
        ("Nb₂O₅–REE", "Nb2O5", "Ce2O3", "Если Ce хранится как Ce₂O₃."),
        ("Nb₂O₅–TiO₂", "Nb2O5", "TiO2", "Обзор Nb–Ti вариации."),
    ),
    "nepheline": (
        ("Na₂O–K₂O", "Na2O", "K2O", "Первый обзор нефелина."),
        ("SiO₂–K₂O", "SiO2", "K2O", "Удобно видеть эволюцию щелочного полевого шпата/фельдшпатоида."),
    ),
    "carbonate": (
        ("MgO–FeO", "MgO", "FeO", "Быстрый обзор Mg–Fe карбонатов."),
        ("SrO–BaO", "SrO", "BaO", "Если Sr и Ba измерены."),
    ),
    "titanite": (
        ("Al₂O₃–TiO₂", "Al2O3", "TiO2", "Первый обзор титанита."),
        ("F–Al₂O₃", "F", "Al2O3", "Если F измерен."),
    ),
    "zircon": (
        ("HfO₂–ZrO₂", "HfO2", "ZrO2", "Первый обзор Zr–Hf вариаций."),
        ("UO₂–ThO₂", "UO2", "ThO2", "Если U и Th измерены как оксиды."),
    ),
}

_TERNARY: dict[str, tuple[str, str]] = {
    "clinopyroxene": ("Wo–En–Fs", "Классификационная ternary после APFU; применимость проверяется отдельно."),
    "orthopyroxene": ("Wo–En–Fs", "Классификационная ternary после APFU."),
    "feldspar": ("An–Ab–Or", "Классическая feldspar ternary; структурный полиморф не угадывается."),
    "garnet": ("Prp–Alm–Grs", "Быстрый compositional обзор после APFU."),
}


def recommendations(mineral_key: str, columns: Iterable[str], *, limit: int = 4) -> list[PlotRecommendation]:
    available = {str(value) for value in columns}
    key = str(mineral_key or "generic")
    result: list[PlotRecommendation] = []
    for title, x, y, note in _XY_CANDIDATES.get(key, ()):
        if x in available and y in available:
            result.append(PlotRecommendation(title=title, route="plots", x=x, y=y, note=note))
        if len(result) >= limit:
            return result
    ternary = _TERNARY.get(key)
    if ternary and len(result) < limit:
        result.append(PlotRecommendation(title=ternary[0], route="ternary", note=ternary[1]))
    if not result:
        numeric_priority = [
            value for value in ("SiO2", "TiO2", "Al2O3", "MgO", "FeO", "FeOt", "CaO", "Na2O", "K2O")
            if value in available
        ]
        if len(numeric_priority) >= 2:
            result.append(PlotRecommendation(
                title=f"{numeric_priority[0]}–{numeric_priority[1]}", route="plots",
                x=numeric_priority[0], y=numeric_priority[1],
                note="Нейтральный старт: оси можно сразу изменить в обычном редакторе.",
            ))
    return result[:limit]
