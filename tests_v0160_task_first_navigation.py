from __future__ import annotations

from petrolab.ui.navigation import PRIMARY_NAV, ROUTE_LABELS, TOOL_SECTIONS


def main() -> None:
    assert PRIMARY_NAV == [
        ("home", "Обзор"),
        ("workspace", "Образцы"),
        ("rock_workspace", "Породы"),
        ("search", "Поиск"),
        ("thin_section", "Шлифы"),
        ("analyses", "Анализы"),
        ("add_data", "Добавить"),
    ]
    assert ROUTE_LABELS["rock_workspace"] == "Породы"
    assert ROUTE_LABELS["plots"] == "Графики"
    assert ROUTE_LABELS["statistics"] == "Статистика"
    assert ROUTE_LABELS["publish"] == "Публикация"
    assert any(route == "plots" for entries in TOOL_SECTIONS.values() for route, _ in entries)
    print("PetroLab v0.16 task-first navigation: OK")


if __name__ == "__main__":
    main()
