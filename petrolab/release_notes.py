from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReleaseNote:
    version: str
    title: str
    items: tuple[str, ...]


RELEASE_NOTES: tuple[ReleaseNote, ...] = (
    ReleaseNote(
        "0.10.2",
        "Bootstrap, повторная изотопия и проверка интерфейса",
        (
            "Инициализация хранилища стала явной: app.py вызывает полный storage bootstrap без package-level monkey-patch.",
            "Старые базы автоматически мигрируют с прежней rock_isotopes-схемы без потери изотопных записей.",
            "Одна порода теперь может хранить несколько определений одного isotope ratio с меткой aliquot/определения и источником.",
            "Wide-view не перезаписывает повторные отношения: используются пользовательские метки или безопасные rep 1, rep 2.",
            "Windows CI запускает настоящий headless Chrome, проверяет desktop/tablet/mobile CSS-viewports и сохраняет screenshots как artifact.",
        ),
    ),
    ReleaseNote(
        "0.10.1",
        "Аудит научной семантики и надёжности",
        (
            "Исправлены опасные автоматические подстановки FeO/FeOt и NiO/Ni в научных шаблонах.",
            "Grütter G10 и whole-rock Mg# теперь корректно учитывают раздельно заданные FeO + Fe2O3.",
            "Primitive-mantle spider получает K, P и Ti из K2O/P2O5/TiO2 только через явный стехиометрический пересчёт.",
            "Журнальные таблицы сохраняют <DL/BDL-текст и определяют trace elements по семантике колонки, а не по совпадению букв.",
            "Whole-rock batch import стал транзакционным: ошибка одной строки откатывает всю пачку.",
            "Ч/б и журнальные presets унифицированы для scientific, whole-rock и ternary рисунков.",
            "Добавлены regression-тесты на выявленные во время повторного аудита тихие ошибки.",
        ),
    ),
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
