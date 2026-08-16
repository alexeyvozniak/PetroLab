from __future__ import annotations

from pathlib import Path


def main() -> None:
    app = Path("app.py").read_text(encoding="utf-8")
    navigation = Path("petrolab/ui/navigation.py").read_text(encoding="utf-8")
    pages = Path("petrolab/ui/pages/__init__.py").read_text(encoding="utf-8")
    package = Path("petrolab/__init__.py").read_text(encoding="utf-8")

    for marker in [
        '"publication_composer": render_publication_composer_page',
        '"grain_profile": render_grain_profile_page',
        '"rock_workspace": render_rock_workspace_page',
        '"multi_panel": render_multi_panel_page',
    ]:
        assert marker in app, marker

    # User-facing research/publication tools stay in the visible task navigation.
    for marker in [
        '("publication_composer", "Собрать рисунок A/B/C")',
        '("multi_panel", "Сравнить на нескольких диаграммах")',
        '("grain_profile", "Профиль по зерну")',
    ]:
        assert marker in navigation, marker

    # Low-level rock editors remain routable for old links and internal actions,
    # but no longer compete for space in the normal sidebar.
    for marker in [
        '"rock_workspace": "Породы"',
        '"rocks": "Редактор пород"',
    ]:
        assert marker in navigation, marker
    assert '("rock_workspace", "Породы")' not in navigation
    assert '("rocks", "Редактор пород")' not in navigation

    for marker in [
        "from .publication_composer import render_publication_composer_page",
        "from .grain_profile import render_grain_profile_page",
        "from .multi_panel import render_multi_panel_page",
        "from .rock_workspace import render_rock_workspace_page",
        "from .v0153_grain_profile_wrappers import render_global_search_page",
        "from .v0154_rock_workspace_wrappers import render_rocks_page",
    ]:
        assert marker in pages, marker
    assert "from .v0152_publication_wrappers import render_multi_panel_page" not in pages
    assert "render_multi_panel_page_v0154_bridge as render_multi_panel_page" not in pages

    # Release keeps earlier non-UI scientific/runtime safety hooks until each is
    # explicitly replaced. UI wrapper accumulation is no longer a requirement.
    for marker in [
        "_install_import_runtime", "_install_physical_point_safety", "_install_amphibole_runtime",
    ]:
        assert marker in package, marker

    print("v0.15.7 route stack tests: OK")


if __name__ == "__main__":
    main()
