from __future__ import annotations

from petrolab.ui.navigation import PRIMARY_NAVIGATION, PRIMARY_NAV_SECTIONS, ROUTE_LABELS, SECONDARY_NAV_SECTIONS


def main() -> None:
    assert PRIMARY_NAVIGATION == [
        ("home", "Обзор"),
        ("add_data", "Добавить данные"),
        ("search", "Найти в проектах"),
        ("samples", "Образцы"),
        ("slides", "Шлифы"),
        ("rocks", "Породы"),
        ("analyses", "Анализы"),
        ("plots", "Графики"),
    ]
    assert list(PRIMARY_NAV_SECTIONS) == ["Начать", "Материал", "Анализы и графики"]
    assert ROUTE_LABELS["rocks"] == "Породы"
    assert ROUTE_LABELS["plots"] == "Графики"
    assert ROUTE_LABELS["statistics"] == "Статистика"
    assert ROUTE_LABELS["figure_recipes"] == "Figure Recipe"
    assert any(route == "figure_recipes" for entries in SECONDARY_NAV_SECTIONS.values() for route, _ in entries)
    print("PetroLab v0.16 task-first navigation: OK")


if __name__ == "__main__":
    main()
