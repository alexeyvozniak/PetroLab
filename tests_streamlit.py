from __future__ import annotations

import gc
import os
import tempfile
from pathlib import Path

import pandas as pd


def seed_database(base: Path) -> None:
    os.environ["PETROLAB_DATA_DIR"] = str(base / "data")
    from petrolab.db import add_dataset, create_project, ensure_storage, replace_dataset_rows
    from petrolab.repositories.rock_repository import create_rock, replace_composition

    ensure_storage()
    project_id = create_project("UI smoke", "Streamlit AppTest")
    frame = pd.DataFrame({
        "Sample": ["A1", "A2", "A3"],
        "Grain": ["G1", "G1", "G1"],
        "Point": ["P1", "P2", "P3"],
        "Generation": ["core", "rim", "core"],
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


def _sidebar_button(app, label: str):
    for button in app.sidebar.button:
        if button.label == label:
            return button
    raise AssertionError(
        f"Sidebar route not found: {label}; available={[button.label for button in app.sidebar.button]}"
    )


def open_page(app, label: str, expected_route: str) -> None:
    _sidebar_button(app, label).click()
    app.run(timeout=30)
    assert_no_exceptions(app, label)
    assert_single_project_context(app, label)
    assert str(app.session_state["nav_route"]) == expected_route, (
        label, app.session_state["nav_route"]
    )


def assert_primary_navigation(app) -> None:
    expected = [
        "Главная", "Данные", "Графики", "Статистика", "Шлифы и изображения",
        "Расчёты", "Публикация", "Поиск", "Настройки",
    ]
    actual = [button.label for button in app.sidebar.button]
    missing = [label for label in expected if label not in actual]
    assert not missing, f"Primary task navigation is incomplete: {missing}; actual={actual}"
    for legacy in ["Минералогические модули", "Быстрый импорт", "Новые анализы", "Редактор пород"]:
        assert legacy not in actual, f"Implementation route leaked into primary sidebar: {legacy}"


def assert_data_workspace_defaults_to_existing_dataset(app) -> None:
    """The primary Data task must never be blank while working datasets exist."""
    open_page(app, "Данные", "workspace")
    assert str(app.session_state["workspace_mode"]) == "Массив данных", app.session_state["workspace_mode"]
    selectors = [widget for widget in app.selectbox if widget.label == "Массив данных"]
    assert selectors, "Data workspace did not expose the existing dataset selector"
    assert len(app.data_editor) > 0, "Data workspace did not render the analysis working table"


def assert_back_restores_route(app) -> None:
    open_page(app, "Данные", "workspace")
    open_page(app, "Графики", "plots")
    _sidebar_button(app, "← Назад").click()
    app.run(timeout=30)
    assert_no_exceptions(app, "Back to Data")
    assert str(app.session_state["nav_route"]) == "workspace", app.session_state["nav_route"]


def assert_hidden_routes_remain_addressable(app) -> None:
    # Compatibility routes are intentionally not menu items, but old recipes and
    # contextual actions can still navigate to them.
    for route in ["formulae", "generations", "grain_profile", "multi_panel"]:
        app.session_state["nav_route"] = route
        app.run(timeout=30)
        assert_no_exceptions(app, f"hidden route {route}")
        assert str(app.session_state["nav_route"]) == route


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
        assert_primary_navigation(app)
        assert_data_workspace_defaults_to_existing_dataset(app)
        assert_back_restores_route(app)

        pages = [
            ("Главная", "home"),
            ("Данные", "workspace"),
            ("Графики", "plots"),
            ("Статистика", "statistics"),
            ("Шлифы и изображения", "thin_section"),
            ("Расчёты", "calculate"),
            ("Публикация", "publish"),
            ("Поиск", "search"),
            ("Настройки", "settings"),
        ]
        for label, route in pages:
            open_page(app, label, route)
        assert_hidden_routes_remain_addressable(app)
        print("streamlit linked-workflow smoke test: OK")
    finally:
        app = None
        gc.collect()
        tmp.cleanup()


if __name__ == "__main__":
    main()
