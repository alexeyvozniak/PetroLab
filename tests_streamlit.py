from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd


def seed_database(base: Path) -> None:
    os.environ["PETROLAB_DATA_DIR"] = str(base / "data")
    from petrolab.db import add_dataset, create_project, ensure_storage, replace_dataset_rows
    from petrolab.minerals.registry import MINERALS
    from petrolab.repositories.rock_repository import create_rock, replace_composition

    ensure_storage()
    project_id = create_project("UI smoke", "Streamlit AppTest")
    frame = pd.DataFrame(
        {
            "Sample": ["A1", "A2", "A3"],
            "Group": ["core", "rim", "core"],
            "SiO2": [40.0, 41.0, 42.0],
            "Al2O3": [12.0, 13.0, 14.0],
            "TiO2": [3.0, 4.0, 5.0],
            "MgO": [20.0, 19.0, 18.0],
            "FeO": [8.0, 9.0, 10.0],
            "K2O": [10.0, 10.0, 10.0],
            "Rb [µg/g]": [150.0, 200.0, 250.0],
            "La [µg/g]": [20.0, 22.0, 24.0],
            "Ce [µg/g]": [45.0, 48.0, 51.0],
        }
    )
    frame = MINERALS["mica"].calculate(frame)
    csv_path = base / "ui.csv"
    frame.to_csv(csv_path, index=False)
    dataset_id = add_dataset(
        project_id=project_id,
        name="UI mica",
        mineral_key="mica",
        source_filename="ui.xlsx",
        source_sheet="Mica",
        source_sha256="test",
        csv_path=str(csv_path),
        row_count=len(frame),
        source_path="",
        source_kind="upload",
        header_row=1,
        column_map={},
        sync_enabled=False,
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


def open_page(app, group: str, page: str) -> None:
    app.sidebar.selectbox[0].set_value(group)
    app.run(timeout=30)
    assert_no_exceptions(app, f"group {group}")
    app.sidebar.radio[0].set_value(page)
    app.run(timeout=30)
    assert_no_exceptions(app, page)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_ui_") as tmp:
        base = Path(tmp)
        seed_database(base)
        from streamlit.testing.v1 import AppTest

        app = AppTest.from_file("app.py", default_timeout=30).run(timeout=30)
        assert_no_exceptions(app, "Главная")

        page_groups = {
            "Работа с данными": ["Проекты", "Источники и импорт", "Единая база", "Расчёты и формулы"],
            "Графики и статистика": ["XY-диаграммы", "Треугольные диаграммы", "Научные диаграммы", "Статистика и кластеры"],
            "Породы и изображения": ["Породы", "Изображения минералов", "Справочник минералов"],
            "Публикация": ["Таблицы для статьи", "Экспорт"],
            "Справка и настройки": ["Что нового", "Инструкция", "Настройки", "Журнал изменений"],
        }
        for group, pages in page_groups.items():
            for page in pages:
                open_page(app, group, page)
        print("streamlit UI smoke test: OK")


if __name__ == "__main__":
    main()
