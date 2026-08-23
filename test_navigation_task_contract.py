from __future__ import annotations

from petrolab.ui.navigation import PRIMARY_NAV, TOOL_SECTIONS


def test_primary_navigation_matches_daily_user_workflow() -> None:
    routes = [route for route, _label in PRIMARY_NAV]
    assert routes == [
        "home",
        "add_data",
        "search",
        "workspace",
        "plots",
        "thin_section",
        "calculate",
        "publish",
        "settings",
    ]


def test_add_data_is_not_hidden_in_advanced_tools() -> None:
    advanced_routes = {
        route
        for entries in TOOL_SECTIONS.values()
        for route, _label in entries
    }
    assert "add_data" not in advanced_routes


def test_core_task_labels_are_user_facing() -> None:
    labels = dict(PRIMARY_NAV)
    assert labels["add_data"] == "Добавить данные"
    assert labels["workspace"] == "Данные и выборка"
    assert labels["plots"] == "Графики и сравнение"
    assert labels["thin_section"] == "Шлифы и фото"
