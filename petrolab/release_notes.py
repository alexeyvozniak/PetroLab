from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReleaseNote:
    version: str
    title: str
    items: tuple[str, ...]


RELEASE_NOTES: tuple[ReleaseNote, ...] = (
    ReleaseNote(
        "0.10.0",
        "Научное рабочее пространство",
        (
            "Научные preset'ы для минералов кимберлитов и лампрофиров.",
            "REE/spider, гистограммы, boxplot и статистика.",
            "Журнальные preset'ы рисунков и таблиц.",
            "Новый модуль пород и связей минерал–порода.",
            "Окно обновлений, настройки и встроенная инструкция.",
        ),
    ),
    ReleaseNote(
        "0.9.2",
        "Классификационные ternary-поля",
        (
            "Morimoto pyroxene overlay.",
            "Ab–An–Or feldspar overlay.",
            "Prp–Alm–Grs и Prp–Alm–Sps проекции гранатов.",
        ),
    ),
    ReleaseNote(
        "0.9.0",
        "Треугольные диаграммы",
        (
            "Универсальный ternary engine.",
            "Публикационный SVG/PNG и интерактивный выбор точек.",
        ),
    ),
    ReleaseNote(
        "0.8.0",
        "Интерактивные точки",
        (
            "Click/box/lasso в Plotly.",
            "Рабочие группы и карточки анализов с изображениями.",
        ),
    ),
    ReleaseNote(
        "0.7.0",
        "Производные расчёты и выбросы",
        (
            "Сохранение APFU/end-member результатов в рабочую базу.",
            "MAD/IQR и ручное исключение точек без удаления исходных данных.",
        ),
    ),
)
