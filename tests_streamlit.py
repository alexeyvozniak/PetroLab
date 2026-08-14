from __future__ import annotations

import gc
import os
import tempfile
from pathlib import Path

import pandas as pd


def seed_database(base: Path) -> None:
    os.environ["PETROLAB_DATA_DIR"] = str(base / "data")
    from petrolab.db import (
        add_dataset,
        create_project,
        ensure_storage,
        replace_dataset_rows,
        save_plot_recipe,
    )
    from petrolab.repositories.rock_repository import create_rock, replace_composition

    ensure_storage()
    project_id = create_project("UI smoke", "Streamlit AppTest")
    frame = pd.DataFrame({
        "Sample": ["A1", "A2", "A3"], "Generation": ["core", "rim", "core"],
        "SiO2": [40.0, 41.0, 42.0], "Al2O3": [12.0, 13.0, 14.0],
        "TiO2": [3.0, 4.0, 5.0], "MgO": [20.0, 19.0, 18.0],
        "FeOt": [8.0, 9.0, 10.0], "K2O": [10.0, 10.0, 10.0],
        "Rb [µg/g]": [150.0, 200.0, 250.0],
        "La [µg/g]": [20.0, 22.0, 24.0], "Ce [µg/g]": [45.0, 48.0, 51.0],
    })
    csv_path = base / "ui.csv"
    frame.to_csv(csv_path, index=False)
    dataset_id = add_dataset(
        project_id=project_id, name="UI mica", mineral_key="mica",
        source_filename="ui.xlsx", source_sheet="Mica", source_sha256="test",
        csv_path=str(csv_path), row_count=len(frame), source_path="", source_kind="upload",
        header_row=1, column_map={}, sync_enabled=False,
    )
    replace_dataset_rows(dataset_id, frame, source_rows=[2, 3, 4])
    save_plot_recipe(
        "UI destructive recipe",
        {"x": "SiO2", "y": "TiO2", "dataset_ids": [dataset_id]},
        project_id,
    )
    rock_id = create_rock(project_id, "UI rock", massif="Kola", lithology="lamprophyre")
    replace_composition(
        rock_id,
        {"SiO2": 44.0, "Na2O": 2.5, "K2O": 3.0, "MgO": 12.0, "FeOt": 10.0, "La [µg/g]": 23.7, "Ce [µg/g]": 61.3},
        units={"La [µg/g]": "µg/g", "Ce [µg/g]": "µg/g"},
    )


def assert_no_exceptions(app, page: str) -> None:
    if len(app.exception):
        details = "\n".join(str(item.value) for item in app.exception)
        raise AssertionError(f"Streamlit page {page!r} raised exceptions:\n{details}")


def assert_single_project_context(app, page: str) -> None:
    duplicates = [widget for widget in app.selectbox if widget.label == "Текущий проект"]
    assert not duplicates, f"Page {page!r} rendered a second project selector despite the sidebar context"


def open_page(app, label: str) -> None:
    buttons = {button.label: button for button in app.sidebar.button}
    if label not in buttons:
        raise AssertionError(f"Sidebar route not found: {label}; available={list(buttons)}")
    buttons[label].click()
    app.run(timeout=30)
    assert_no_exceptions(app, label)
    assert_single_project_context(app, label)


def _selectbox(app, label: str):
    for widget in app.selectbox:
        if widget.label == label:
            return widget
    raise AssertionError(f"Selectbox not found: {label}")


def _button(app, label: str):
    for widget in app.button:
        if widget.label == label:
            return widget
    raise AssertionError(f"Button not found: {label}")


def assert_recipe_delete_requires_second_click(app) -> None:
    from petrolab.db import list_plot_recipes

    open_page(app, "XY-диаграммы")
    selector = _selectbox(app, "Загрузить рецепт")
    option = next(value for value in selector.options if str(value).startswith("UI destructive recipe"))
    selector.set_value(option)
    app.run(timeout=30)
    assert_no_exceptions(app, "XY-диаграммы / recipe selection")

    before = list_plot_recipes()
    assert any(record["name"] == "UI destructive recipe" for record in before)
    _button(app, "Удалить рецепт").click()
    app.run(timeout=30)
    assert_no_exceptions(app, "XY-диаграммы / first delete click")
    after_first = list_plot_recipes()
    assert any(record["name"] == "UI destructive recipe" for record in after_first), (
        "First destructive click must not delete the recipe"
    )
    assert any("Удаление рецепта" in str(item.value) for item in app.warning), (
        "First destructive click must expose a confirmation warning"
    )

    _button(app, "Удалить рецепт").click()
    app.run(timeout=30)
    assert_no_exceptions(app, "XY-диаграммы / confirmed recipe delete")
    after_second = list_plot_recipes()
    assert not any(record["name"] == "UI destructive recipe" for record in after_second)


def main() -> None:
    tmp = tempfile.TemporaryDirectory(prefix="petrolab_ui_")
    app = None
    try:
        base = Path(tmp.name)
        seed_database(base)
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=30).run(timeout=30)
        assert_no_exceptions(app, "Главная")
        assert_single_project_context(app, "Главная")
        assert_recipe_delete_requires_second_click(app)
        pages = [
            "Главная", "Новые анализы", "База анализов", "Расчёты",
            "XY-диаграммы", "Треугольные", "Научные диаграммы", "Статистика",
            "Породы", "Изображения", "Минералогические модули",
            "Таблицы для статьи", "Экспорт", "Проекты", "Настройки",
            "Справка", "Что нового", "История правок данных",
        ]
        for page in pages:
            open_page(app, page)
        print("streamlit UI smoke test: OK")
    finally:
        app = None
        gc.collect()
        tmp.cleanup()


if __name__ == "__main__":
    main()
