from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "petrolab" / "ui"
PAGES = UI / "pages"
THEME = (UI / "theme.py").read_text(encoding="utf-8")
LAYOUT = (UI / "layout.py").read_text(encoding="utf-8")
NAVIGATION = (UI / "navigation.py").read_text(encoding="utf-8")
COMPONENTS = (UI / "components.py").read_text(encoding="utf-8")
PROJECT_CONTEXT = (UI / "project_context.py").read_text(encoding="utf-8")
XY_COMPONENTS = (UI / "xy_components.py").read_text(encoding="utf-8")
SOURCE_CONTROLS = (UI / "source_controls.py").read_text(encoding="utf-8")
IMAGE_COMPONENTS = (UI / "image_components.py").read_text(encoding="utf-8")
DESTRUCTIVE_ACTIONS = (UI / "destructive_actions.py").read_text(encoding="utf-8")
PLOT_ACTIONS = (UI / "plot_actions.py").read_text(encoding="utf-8")
SCIENCE = (PAGES / "science_plots.py").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")

# Scientific-dashboard visual system, accessibility and responsive behavior.
for token in ["--petro-bg", "--petro-surface", "--petro-text", "--petro-accent", "--petro-success", "--petro-warning", "--petro-danger"]:
    assert token in THEME, token
assert "--petro-text-muted: #596663" in THEME
assert "focus-visible" in THEME
assert "@media (max-width: 1100px)" in THEME
assert "@media (max-width: 760px)" in THEME
assert "overflow-x: auto" in THEME
assert "max-width" in THEME
assert "<h1 class=\"petrolab-page-title\">" in LAYOUT
assert "<h2 class=\"petrolab-section-title\">" in LAYOUT
assert "render_page_header" in LAYOUT and "render_badges" in LAYOUT

# One global project context: sidebar owns selection; routed pages do not render local project selectors.
for marker in ["ACTIVE_PROJECT_KEY", "def active_project(", "def active_project_id(", "def set_active_project("]:
    assert marker in PROJECT_CONTEXT, marker
assert "active_project_id" in NAVIGATION and "set_active_project" in NAVIGATION
assert 'st.session_state.get("_sidebar_project_ready")' in COMPONENTS
assert "Compatibility fallback for standalone page/AppTest" in COMPONENTS
for page_name in [
    "home_dashboard.py", "sources_dashboard.py", "analyses_dashboard.py", "formulae.py",
    "plots_dashboard.py", "rocks.py", "images_dashboard.py", "slides.py",
]:
    text = (PAGES / page_name).read_text(encoding="utf-8")
    assert "project_context" in text, f"page still resolves project state independently: {page_name}"

# The refactor is authoritative: no runtime page-policy modules or parallel legacy pages may return.
for obsolete in [
    UI / "import_page_policy.py",
    UI / "plot_page_policy.py",
    UI / "image_page_policy.py",
    UI / "science_page_policy.py",
    UI / "destructive_page_policy.py",
    PAGES / "home.py",
    PAGES / "sources.py",
    PAGES / "analyses.py",
    PAGES / "images.py",
    PAGES / "plots.py",
]:
    assert not obsolete.exists(), f"obsolete UI layer returned: {obsolete.name}"
assert not list(UI.glob("*_page_policy.py")), "runtime page policy module returned"
for bootstrap in [
    "install_import_page_policy", "install_plot_page_policy", "install_destructive_page_policy",
    "install_image_page_policy", "install_science_page_policy",
]:
    assert bootstrap not in APP, bootstrap

sources_dashboard = (PAGES / "sources_dashboard.py").read_text(encoding="utf-8")
for marker in ["import_linked_sheets", "import_uploaded_sheets", "header_rows=headers", "mineral_keys=minerals"]:
    assert marker in sources_dashboard, marker
assert "from petrolab.ui.pages import sources as legacy" not in sources_dashboard

analyses = (PAGES / "analyses_dashboard.py").read_text(encoding="utf-8")
assert "analysis_components" in analyses
assert "from petrolab.ui.pages import analyses" not in analyses
for view in ["Основное", "Химия", "Расчёты", "QC", "Все"]:
    assert view in analyses

images = (PAGES / "images_dashboard.py").read_text(encoding="utf-8")
assert "image_components" in images
assert "from petrolab.ui.pages import images" not in images
assert "render_project_selector" not in images
assert "st.columns([1.35, 1])" in images
assert "confirm_delete_image_" in images
for marker in [
    'for column in ("Sample", "Grain", "Generation", "Point")',
    "limit = 5000",
    "valid_previous",
    "semantic field-link",
]:
    assert marker in IMAGE_COMPONENTS, marker

slides = (PAGES / "slides.py").read_text(encoding="utf-8")
for marker in ["render_slides_page", "Шлифы и поля", "Оригинал остаётся", "Одна метка может связать EPMA, ЭДС и LA"]:
    assert marker in slides, marker
assert '("slides", "Шлифы и поля")' in NAVIGATION
assert '"slides": render_slides_page' in APP

# XY quick/advanced workspaces and guarded actions have explicit owners.
advanced = (PAGES / "plots_advanced.py").read_text(encoding="utf-8")
plots = (PAGES / "plots_dashboard.py").read_text(encoding="utf-8")
for marker in [
    "def render_advanced_xy_workspace(", "render_outlier_controls", "render_advanced_interactive",
    "Сохранённый рецепт ссылается на наборы", "В график входит", "save_plot_recipe",
]:
    assert marker in advanced, marker
for marker in [
    "def render_quick_interactive(", "def render_advanced_interactive(",
    'key="petrolab_quick_interactive_plot"', 'key="petrolab_advanced_interactive_plot"',
    "default_outlier_method", "Внутри групп", "hidden_saved", "sanitize_xy_rows",
    "from petrolab.ui.plot_actions import clear_work_group",
]:
    assert marker in XY_COMPONENTS, marker
for marker in ["delete_plot_recipe", "delete_style_profile", "clear_work_group", "confirm_then", "render_plot_confirmations"]:
    assert marker in PLOT_ACTIONS, marker
assert "from petrolab.ui.pages import plots" not in advanced + XY_COMPONENTS
assert "_petrolab_workspace_call_index" not in APP + plots + XY_COMPONENTS
assert "render_advanced_xy_workspace(project_id)" in plots
for marker in [
    "Видимые статьи / источники", "Показать все источники", "Скрыть все источники",
    "Данные остаются в базе", "filter_visible_sources",
]:
    assert marker in SOURCE_CONTROLS, marker
database_browser = (PAGES / "database_browser.py").read_text(encoding="utf-8")
for text in [database_browser, plots, advanced]:
    assert "attach_study_metadata" in text
assert "Источник / статья" in database_browser
assert "visible_sources" in plots and "hidden_sources" in plots
assert "visible_sources" in advanced and "hidden_sources" in advanced

# Science safeguards are direct page behavior, not monkeypatches.
for marker in [
    "def _mineral_filtered_presets(",
    "require_known_units=True",
    "_PATTERN_YLABELS",
    "def _apply_pattern_group_styles(",
    "def _sync_science_axis_defaults(",
    "matches_preset",
    "Пользовательские оси: литературное название, source citation и overlay preset'а отключены.",
    "Grouped boxplot требует ровно один числовой параметр",
    'key="hist_svg"',
    'key="box_svg"',
    "render_page_header",
]:
    assert marker in SCIENCE, marker

# Navigation is flat/grouped: no second-stage workspace selector.
assert "render_sidebar" in APP
assert "PAGE_GROUPS" not in APP
assert "Рабочая область" not in APP
for label in ["Данные", "Исследование", "Материалы", "Публикация", "Система"]:
    assert label in NAVIGATION
for label in ["Главная", "Новые анализы", "База анализов", "Расчёты", "XY-диаграммы", "Изображения", "История правок данных"]:
    assert label in NAVIGATION

# High-value dashboard pages use the shared visual hierarchy.
for page_name in [
    "home_dashboard.py", "sources_dashboard.py", "analyses_dashboard.py",
    "plots_dashboard.py", "images_dashboard.py", "settings.py", "statistics.py",
    "formulae.py", "help.py", "rocks.py", "science_plots.py",
]:
    path = PAGES / page_name
    assert path.exists(), page_name
    text = path.read_text(encoding="utf-8")
    assert "render_page_header" in text, f"dashboard page lacks shared header: {page_name}"

settings = (PAGES / "settings.py").read_text(encoding="utf-8")
assert 'st.tabs(' in settings
assert '"Интерфейс"' in settings and '"Рисунки"' in settings and '"Таблицы"' in settings and '"Анализ"' in settings
assert '"Быстрое построение"' in plots and '"Расширенный редактор"' in plots
assert "FIGURE_PRESETS" in plots
for marker in ["preset.width_in", "preset.height_in", "preset.font_family", "preset.font_size", "preset.tick_size", "preset.spine_width", "preset.dpi"]:
    assert marker in plots, f"Quick XY does not apply configured preset field: {marker}"
assert 'f"{preset.title}' in plots
home = (PAGES / "home_dashboard.py").read_text(encoding="utf-8")
assert "def _action(" not in home
assert home.count('key=f"home_{route}"') == 1

# Destructive actions are explicit and reusable, never installed dynamically.
for marker in ["def confirm_then(", "def render_pending(", "_pending_destructive_"]:
    assert marker in DESTRUCTIVE_ACTIONS, marker
rocks = (PAGES / "rocks.py").read_text(encoding="utf-8")
for marker in [
    "confirm_then(\"rock_links\"", "confirm_then(\"rock_image\"", "render_pending(",
    "set_mineral_links as _set_mineral_links", "delete_rock_image as _delete_rock_image",
]:
    assert marker in rocks, marker
assert "render_project_selector" not in rocks

for path in sorted(PAGES.glob("*.py")):
    text = path.read_text(encoding="utf-8")
    assert "use_container_width" not in text, f"deprecated width API in {path.name}"
    for match in re.finditer(r"width\s*=\s*(\d+)", text):
        width = int(match.group(1))
        assert width <= 1600, f"suspicious fixed width {width}px in {path.name}"

print("UI dashboard structure tests: OK")
