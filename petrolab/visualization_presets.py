from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class ScientificPlotPreset:
    preset_id: str
    title: str
    mineral_key: str | None
    plot_type: str
    x: str = ""
    y: str = ""
    components: tuple[str, str, str] | None = None
    x_label: str = ""
    y_label: str = ""
    source: str = ""
    doi: str = ""
    overlay_id: str | None = None
    note: str = ""


@dataclass(frozen=True)
class PointStylePreset:
    preset_id: str
    title: str
    markers: tuple[str, ...]
    filled: bool = True
    alpha: float = 0.9
    size_multiplier: float = 1.0
    note: str = ""


@dataclass(frozen=True)
class FigurePreset:
    title: str
    width_in: float
    height_in: float
    font_family: str
    font_size: float
    tick_size: float
    label_size: float
    legend_size: float
    marker_size: float
    line_width: float
    spine_width: float
    dpi: int
    monochrome: bool = False
    grid: bool = False


@dataclass(frozen=True)
class TablePreset:
    title: str
    font_family: str
    font_size: float
    header_size: float
    decimals_major: int
    decimals_trace: int
    landscape: bool
    repeat_header: bool = True
    note: str = ""


SCIENTIFIC_PLOT_PRESETS: Final[dict[str, ScientificPlotPreset]] = {
    "mica_mitchell_al_ti": ScientificPlotPreset(
        preset_id="mica_mitchell_al_ti",
        title="Слюды: Al₂O₃–TiO₂ (кимберлиты/лампрофиры)",
        mineral_key="mica",
        plot_type="xy",
        x="Al2O3",
        y="TiO2",
        x_label="Al₂O₃, wt.%",
        y_label="TiO₂, wt.%",
        source="Mitchell (1995), Kimberlites, Orangeites, and Related Rocks",
        note="Оси и смысл диаграммы литературные. Поля/эволюционные линии не зашиваются без проверенных координат.",
    ),
    "mica_mitchell_al_fe": ScientificPlotPreset(
        preset_id="mica_mitchell_al_fe",
        title="Слюды: Al₂O₃–FeOₜ (кимберлиты/лампрофиры)",
        mineral_key="mica",
        plot_type="xy",
        x="Al2O3",
        y="FeOt",
        x_label="Al₂O₃, wt.%",
        y_label="FeOₜ, wt.%",
        source="Mitchell (1995), Kimberlites, Orangeites, and Related Rocks",
        note="FeOt и FeO не взаимозаменяются автоматически. Если total Fe отсутствует, выберите другую ось вручную и проверьте подпись.",
    ),
    "mica_mgnum_ti": ScientificPlotPreset(
        preset_id="mica_mgnum_ti",
        title="Слюды: Mg#–TiO₂",
        mineral_key="mica",
        plot_type="xy",
        x="Mg#",
        y="TiO2",
        x_label="Mg#",
        y_label="TiO₂, wt.%",
        source="Рабочая минералого-петрологическая диаграмма; применяется в исследованиях кимберлитовых слюд",
    ),
    "mica_mgnum_ba": ScientificPlotPreset(
        preset_id="mica_mgnum_ba",
        title="Слюды: Mg#–BaO",
        mineral_key="mica",
        plot_type="xy",
        x="Mg#",
        y="BaO",
        x_label="Mg#",
        y_label="BaO, wt.%",
        source="Рабочая диаграмма эволюции флогопита в щелочно-ультраосновных системах",
    ),
    "garnet_grutter_ca_cr": ScientificPlotPreset(
        preset_id="garnet_grutter_ca_cr",
        title="Гранат: CaO–Cr₂O₃ (индикаторные минералы кимберлитов)",
        mineral_key="garnet",
        plot_type="xy",
        x="CaO",
        y="Cr2O3",
        x_label="CaO, wt.%",
        y_label="Cr₂O₃, wt.%",
        source="Grütter et al. (2004), Lithos 77, 841–857",
        doi="10.1016/j.lithos.2004.04.012",
        overlay_id="garnet_grutter_g10_diagnostic",
        note="Preset реализует только проверяемые диагностические границы G10/G9 и G10A/G10B; полная G0–G12 классификация требует последовательных условий.",
    ),
    "garnet_mgnum_ti": ScientificPlotPreset(
        preset_id="garnet_mgnum_ti",
        title="Гранат: Mg#–TiO₂",
        mineral_key="garnet",
        plot_type="xy",
        x="Mg#",
        y="TiO2",
        x_label="Mg#",
        y_label="TiO₂, wt.%",
        source="Grütter et al. (2004), Lithos 77, 841–857",
        doi="10.1016/j.lithos.2004.04.012",
        note="Полезно совместно с CaO–Cr₂O₃ для отделения высоко-Ti гранатов.",
    ),
    "ilmenite_wyatt_mg_ti": ScientificPlotPreset(
        preset_id="ilmenite_wyatt_mg_ti",
        title="Ильменит: MgO–TiO₂ (kimberlitic reference line)",
        mineral_key="ilmenite",
        plot_type="xy",
        x="MgO",
        y="TiO2",
        x_label="MgO, wt.%",
        y_label="TiO₂, wt.%",
        source="Wyatt et al. (2004), Lithos 77, 819–840",
        doi="10.1016/j.lithos.2004.04.025",
        overlay_id="ilmenite_wyatt_kimberlite_curve",
    ),
    "ilmenite_mg_cr": ScientificPlotPreset(
        preset_id="ilmenite_mg_cr",
        title="Ильменит: MgO–Cr₂O₃",
        mineral_key="ilmenite",
        plot_type="xy",
        x="MgO",
        y="Cr2O3",
        x_label="MgO, wt.%",
        y_label="Cr₂O₃, wt.%",
        source="Wyatt et al. (2004), Lithos 77, 819–840",
        doi="10.1016/j.lithos.2004.04.025",
        note="Используется совместно с MgO–TiO₂; параболический тренд Cr не является универсальным.",
    ),
    "spinel_crnum_mgnum": ScientificPlotPreset(
        preset_id="spinel_crnum_mgnum",
        title="Шпинель: Cr#–Mg#",
        mineral_key="spinel",
        plot_type="xy",
        x="Cr#",
        y="Mg#",
        x_label="Cr# = Cr/(Cr+Al)",
        y_label="Mg# = Mg/(Mg+Fe²⁺)",
        source="Barnes & Roeder (2001), Journal of Petrology 42, 2279–2302",
        doi="10.1093/petrology/42.12.2279",
        note="Проекция spinel prism. Плотностные поля пород не аппроксимируются без оцифрованных контуров.",
    ),
    "spinel_ti_fe3": ScientificPlotPreset(
        preset_id="spinel_ti_fe3",
        title="Шпинель: TiO₂–Fe³⁺#",
        mineral_key="spinel",
        plot_type="xy",
        x="TiO2",
        y="Fe3#",
        x_label="TiO₂, wt.%",
        y_label="Fe³⁺/(Fe³⁺+Cr+Al)",
        source="Barnes & Roeder (2001), Journal of Petrology 42, 2279–2302",
        doi="10.1093/petrology/42.12.2279",
    ),
    "olivine_fo_nio": ScientificPlotPreset(
        preset_id="olivine_fo_nio",
        title="Оливин: Fo–NiO",
        mineral_key="olivine",
        plot_type="xy",
        x="Fo",
        y="NiO",
        x_label="Fo, mol.%",
        y_label="NiO, wt.%",
        source="Рабочая диаграмма для оценки мантийного cargo и магматической эволюции в кимберлитах/лампрофирах",
        note="EPMA-вариант с NiO, wt.%. Не смешивать автоматически с Ni в µg/g.",
    ),
    "olivine_fo_ni": ScientificPlotPreset(
        preset_id="olivine_fo_ni",
        title="Оливин: Fo–Ni (trace concentration)",
        mineral_key="olivine",
        plot_type="xy",
        x="Fo",
        y="Ni",
        x_label="Fo, mol.%",
        y_label="Ni, µg/g",
        source="Рабочая диаграмма для различения мантийного cargo и магматической эволюции в кимберлитах/лампрофирах",
        note="Требует Ni с известной concentration unit. NiO не подставляется вместо Ni автоматически.",
    ),
    "cpx_na_cr": ScientificPlotPreset(
        preset_id="cpx_na_cr",
        title="Клинопироксен: Na₂O–Cr₂O₃",
        mineral_key="clinopyroxene",
        plot_type="xy",
        x="Na2O",
        y="Cr2O3",
        x_label="Na₂O, wt.%",
        y_label="Cr₂O₃, wt.%",
        source="Рабочая мантийно-ксенокристовая диаграмма для щелочно-ультраосновных пород",
    ),
    "pyroxene_wo_en_fs": ScientificPlotPreset(
        preset_id="pyroxene_wo_en_fs",
        title="Пироксены: En–Fs–Wo (Morimoto)",
        mineral_key="clinopyroxene",
        plot_type="ternary",
        components=("En", "Fs", "Wo"),
        source="Morimoto et al. (1988), Mineralogical Magazine 52, 535–550",
        doi="10.1180/minmag.1988.052.367.15",
        overlay_id="pyroxene_morimoto_1988",
    ),
    "feldspar_ab_an_or": ScientificPlotPreset(
        preset_id="feldspar_ab_an_or",
        title="Полевые шпаты: Ab–An–Or",
        mineral_key="feldspar",
        plot_type="ternary",
        components=("Ab", "An", "Or"),
        source="Deer et al. (1992); Gündüz & Asan (2023), Fig. 5",
        doi="10.1180/mgm.2022.113",
        overlay_id="feldspar_gunduz_asan_2023",
    ),
}


POINT_STYLE_PRESETS: Final[dict[str, PointStylePreset]] = {
    "balanced": PointStylePreset("balanced", "Спокойный научный", ("o", "s", "^", "D", "v", "P", "X"), True, 0.88, 1.0),
    "open": PointStylePreset("open", "Контурные маркеры", ("o", "s", "^", "D", "v", "<", ">"), False, 1.0, 1.05),
    "contrast": PointStylePreset("contrast", "Контрастный", ("o", "^", "s", "X", "D", "P", "v"), True, 0.95, 1.15),
    "compact": PointStylePreset("compact", "Много серий", ("o", "s", "^", "v", "<", ">", "D", "p", "h", "X", "P"), True, 0.78, 0.82),
    "bw": PointStylePreset("bw", "Ч/б для статьи", ("o", "s", "^", "D", "v", "P", "X"), False, 1.0, 1.05, "Используйте форму и заливку вместо цвета."),
}


FIGURE_PRESETS: Final[dict[str, FigurePreset]] = {
    "Custom": FigurePreset("Свой", 7.2, 5.4, "Arial", 10, 9, 10, 9, 58, 1.0, 1.0, 600),
    "Lithos": FigurePreset("Lithos", 7.2, 5.4, "Arial", 9.5, 8.5, 9.5, 8.5, 55, 0.9, 0.9, 600),
    "Geodynamics & Tectonophysics": FigurePreset("Geodynamics & Tectonophysics", 7.0, 5.3, "Arial", 10, 9, 10, 9, 60, 1.0, 1.0, 600),
    "ДАН": FigurePreset("ДАН", 6.7, 5.0, "Arial", 9, 8, 9, 8, 62, 1.0, 1.1, 600, True),
    "Elsevier 1-column": FigurePreset("Elsevier · 1 колонка", 3.54, 3.1, "Arial", 8, 7.5, 8, 7.5, 38, 0.8, 0.8, 600),
    "Elsevier 2-column": FigurePreset("Elsevier · 2 колонки", 7.48, 5.2, "Arial", 9, 8, 9, 8, 52, 0.9, 0.9, 600),
    "Supplementary": FigurePreset("Supplementary", 7.5, 5.8, "Arial", 10, 9, 10, 9, 50, 0.9, 0.9, 600, False, True),
}


TABLE_PRESETS: Final[dict[str, TablePreset]] = {
    "Lithos": TablePreset("Lithos", "Arial", 8.5, 8.5, 2, 1, True, note="Компактная основная/дополнительная таблица; финально сверяйте актуальные author guidelines журнала."),
    "Geodynamics & Tectonophysics": TablePreset("Geodynamics & Tectonophysics", "Arial", 9, 9, 2, 1, True, note="Стартовый preset оформления; финально сверяйте актуальные требования журнала."),
    "ДАН": TablePreset("ДАН", "Arial", 9, 9, 2, 1, True, note="Строгая ч/б основа; финально сверяйте актуальные требования редакции."),
    "Elsevier Supplementary": TablePreset("Elsevier Supplementary", "Arial", 8, 8, 2, 2, True, note="Стартовый supplementary preset; конкретный журнал Elsevier может иметь дополнительные требования."),
    "Рабочая": TablePreset("Рабочая", "Arial", 10, 10, 3, 2, False),
}
