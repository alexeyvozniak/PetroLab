from __future__ import annotations

from pathlib import Path


def main() -> None:
    app = Path("app.py").read_text(encoding="utf-8")
    navigation = Path("petrolab/ui/navigation.py").read_text(encoding="utf-8")
    package = Path("petrolab/__init__.py").read_text(encoding="utf-8")

    # Routes are lazy module/function targets so first paint does not import every
    # scientific page. Product Design screens are explicit route owners. The
    # linked workspace is reached through its Plotly compatibility wrapper.
    for marker in [
        '"figure_recipes": ("petrolab.ui.pages.figure_recipes", "render_figure_recipes_page")',
        '"linked_views": ("petrolab.ui.pages.linked_views_compat", "render_linked_views_reference_page")',
        '"search": ("petrolab.ui.pages.search_reference", "render_search_reference_page")',
        '"slides": ("petrolab.ui.pages.slides_reference", "render_slides_reference_page")',
        '"add_data": ("petrolab.ui.pages.add_data_reference", "render_add_data_reference_page")',
        '"rocks": ("petrolab.ui.pages.rocks", "render_rocks_page")',
        "def _resolve_renderer(",
        "import_module(module_path)",
    ]:
        assert marker in app, marker

    # Everyday rail follows the approved references; specialised tools remain in
    # the secondary disclosure rather than competing with the main workflow.
    for marker in [
        '("samples", "Образцы")',
        '("search", "Поиск")',
        '("slides", "Шлифы")',
        '("linked_views", "Построение")',
        '("add_data", "Добавить")',
        '("rocks", "Породы")',
        '("figure_recipes", "Figure Recipe")',
        '"Ещё"',
    ]:
        assert marker in navigation, marker

    # Release keeps earlier non-UI scientific/runtime safety hooks until each is
    # explicitly replaced. UI wrapper accumulation is no longer a requirement.
    for marker in [
        "_install_import_runtime", "_install_amphibole_runtime", "_install_user_derived_runtime",
    ]:
        assert marker in package, marker

    print("route stack tests: OK")


if __name__ == "__main__":
    main()
