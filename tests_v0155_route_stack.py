from __future__ import annotations

from pathlib import Path


def main() -> None:
    app = Path("app.py").read_text(encoding="utf-8")
    navigation = Path("petrolab/ui/navigation.py").read_text(encoding="utf-8")
    pages = Path("petrolab/ui/pages/__init__.py").read_text(encoding="utf-8")
    package = Path("petrolab/__init__.py").read_text(encoding="utf-8")

    for marker in [
        '"figure_recipes": render_figure_recipes_page',
        '"linked_views": render_linked_views_page',
        '"rocks": render_rocks_page',
    ]:
        assert marker in app, marker

    # Product Design exposes everyday material work first and groups specialised
    # publication/scientific tools under an explicit secondary disclosure.
    for marker in [
        '("rocks", "Породы")',
        '("linked_views", "Связанные представления")',
        '("figure_recipes", "Figure Recipe")',
        '"Дополнительные инструменты"',
    ]:
        assert marker in navigation, marker

    for marker in [
        "from .figure_recipes import render_figure_recipes_page",
        "from .linked_views import render_linked_views_page",
        "from .rocks import render_rocks_page",
    ]:
        assert marker in pages, marker

    # Release keeps earlier non-UI scientific/runtime safety hooks until each is
    # explicitly replaced. UI wrapper accumulation is no longer a requirement.
    for marker in [
        "_install_import_runtime", "_install_amphibole_runtime", "_install_user_derived_runtime",
    ]:
        assert marker in package, marker

    print("v0.15.7 route stack tests: OK")


if __name__ == "__main__":
    main()
