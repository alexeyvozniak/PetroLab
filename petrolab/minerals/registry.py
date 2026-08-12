from __future__ import annotations

from .base import MineralModule

MINERALS: dict[str, MineralModule] = {
    "mica": MineralModule(
        "mica", "Слюды (биотит–флогопит)", "Филлосиликаты",
        "Биотит, флогопит и родственные слюды. IMA 22-charge (11 O-экв.) и отдельная удвоенная 22-O запись для сравнения с литературой.",
        ("SiO2", "TiO2", "Al2O3", "Cr2O3", "FeO", "Fe2O3", "MnO", "MgO", "CaO", "Na2O", "K2O", "F", "Cl"),
    ),
    "amphibole": MineralModule(
        "amphibole", "Амфиболы", "Иносиликаты",
        "Амфиболы по IMA 2012; рутинный пересчёт на 23 O-экв. без небезопасного автоматического имени.",
        ("SiO2", "TiO2", "Al2O3", "Cr2O3", "FeO", "Fe2O3", "MnO", "MgO", "CaO", "Na2O", "K2O", "F", "Cl"),
    ),
    "clinopyroxene": MineralModule(
        "clinopyroxene", "Клинопироксены", "Иносиликаты",
        "Morimoto/IMA; 6 O, Q–J, Wo–En–Fs; основной Fe³⁺-режим — Droop.",
        ("SiO2", "TiO2", "Al2O3", "Cr2O3", "FeO", "Fe2O3", "MnO", "MgO", "CaO", "Na2O"),
    ),
    "orthopyroxene": MineralModule(
        "orthopyroxene", "Ортопироксены", "Иносиликаты",
        "Энстатит–ферросилит; 6 O, Fe³⁺ опционально по Droop.",
        ("SiO2", "TiO2", "Al2O3", "Cr2O3", "FeO", "Fe2O3", "MnO", "MgO", "CaO", "Na2O"),
    ),
    "olivine": MineralModule(
        "olivine", "Оливин", "Несосиликаты",
        "4 O; Fo–Fa–Te–Ca-ol; опциональная стехиометрическая оценка Fe³⁺.",
        ("SiO2", "FeO", "Fe2O3", "MnO", "MgO", "CaO", "NiO"),
    ),
    "garnet": MineralModule(
        "garnet", "Гранаты", "Несосиликаты",
        "IMA-13; 12 O, 8 катионов для режима Droop; Prp–Alm–Sps–Grs/Adr.",
        ("SiO2", "TiO2", "Al2O3", "Cr2O3", "FeO", "Fe2O3", "MnO", "MgO", "CaO"),
    ),
    "feldspar": MineralModule(
        "feldspar", "Полевые шпаты", "Тектосиликаты",
        "8 O; An–Ab–Or и Ba-компонента.",
        ("SiO2", "Al2O3", "FeO", "CaO", "Na2O", "K2O", "BaO"),
    ),
    "nepheline": MineralModule(
        "nepheline", "Нефелин", "Фельдшпатоиды",
        "Henderson (2020): 32 O, стехиометрический QC для 16 T- и 8 полостных позиций.",
        ("SiO2", "TiO2", "Al2O3", "Fe2O3", "CaO", "Na2O", "K2O"),
    ),
    "feldspathoid": MineralModule(
        "feldspathoid", "Фельдшпатоиды", "Тектосиликаты",
        "Нефелин, содалитовая группа и родственные минералы; специализированные схемы будут добавлены по подгруппам.",
        ("SiO2", "Al2O3", "FeO", "CaO", "Na2O", "K2O"),
    ),
    "carbonate": MineralModule(
        "carbonate", "Карбонаты", "Карбонаты",
        "Кальцитовая (ΣCat=1) и доломитовая (ΣCat=2) нормировки.",
        ("FeO", "Fe2O3", "MnO", "MgO", "CaO", "SrO", "BaO"),
    ),
    "spinel": MineralModule(
        "spinel", "Шпинель, магнетит, хромит", "Оксиды",
        "AB2O4; 4 O и 3 катиона, Fe³⁺ по Droop; Cr# и Mg#.",
        ("TiO2", "Al2O3", "Cr2O3", "Fe2O3", "FeO", "MnO", "MgO", "ZnO", "NiO"),
    ),
    "fe_ti_oxide": MineralModule(
        "fe_ti_oxide", "Ильменит–гематитовые оксиды", "Оксиды",
        "Ильменитовая схема на 3 O; стехиометрический Fe³⁺ по Droop.",
        ("TiO2", "Al2O3", "Cr2O3", "Fe2O3", "FeO", "MnO", "MgO"),
    ),
    "perovskite": MineralModule(
        "perovskite", "Перовскит", "Оксиды",
        "ABO3, 3 O; IMA-supergroup (Mitchell et al.) и основа для эндмемберной схемы Locock–Mitchell.",
        ("TiO2", "Nb2O5", "ZrO2", "Al2O3", "Cr2O3", "Fe2O3", "FeO", "CaO", "Na2O", "SrO", "BaO", "La2O3", "Ce2O3", "Nd2O3"),
    ),
    "apatite": MineralModule(
        "apatite", "Апатит", "Фосфаты",
        "Ketcham: 25 O-экв.; F–Cl–OH, с QC отрицательного OH.",
        ("P2O5", "SiO2", "SO3", "CaO", "Na2O", "SrO", "BaO", "La2O3", "Ce2O3", "F", "Cl"),
    ),
    "titanite": MineralModule(
        "titanite", "Титанит", "Силикаты",
        "Пересчёт по схеме MinPlot: сумма тетраэдрической и октаэдрической позиций = 2.",
        ("SiO2", "TiO2", "Al2O3", "Fe2O3", "FeO", "CaO", "Na2O", "F"),
    ),
    "zircon": MineralModule(
        "zircon", "Циркон", "Несосиликаты",
        "ZrSiO4; 4 O с сохранением Hf, Th, U в apfu.",
        ("SiO2", "ZrO2", "HfO2", "ThO2", "UO2"),
    ),
    "generic": MineralModule(
        "generic", "Другой минерал", "Прочее",
        "Универсальный режим: импорт, QC и диаграммы без минералоспецифических предположений.",
        (),
    ),
}


def labels() -> dict[str, str]:
    return {key: module.name_ru for key, module in MINERALS.items()}
