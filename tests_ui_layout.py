from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "petrolab" / "ui"
PAGES = UI / "pages"
THEME = (UI / "theme.py").read_text(encoding="utf-8")
LAYOUT = (UI / "layout.py").read_text(encoding="utf-8")
NAVIGATION = (UI / "navigation.py").read_text(encoding="utf-8")
PAGES_INIT = (PAGES / "__init__.py").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")

# Shared visual system and accessibility remain mandatory.
for token in [
    "--petro-bg", "--petro-surface", "--petro-text", "--petro-accent",
    "--petro-success", "--petro-warning", "--petro-danger",
]:
    assert token in THEME, token
assert "focus-visible" in THEME
assert "@media (max-width: 1100px)" in THEME
assert "@media (max-width: 760px)" in THEME
assert "overflow-x: auto" in THEME
assert "render_page_header" in LAYOUT and "render_badges" in LAYOUT

# No return of runtime page-policy layers or duplicate legacy dashboards.
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

# Canonical Airtable/JMP/Origin interaction architecture.
for ui_file in [
    "selection_context.py", "selection_components.py", "analysis_table.py",
    "navigation_state.py", "plot_spec.py", "linked_panels.py", "xy_components.py",
    "plot_manager.py", "panel_manager.py", "intake_workflow.py", "smart_plot_start.py",
    "table_view_state.py", "field_presets.py", "record_detail.py",
]:
    assert (UI / ui_file).exists(), ui_file
assert (ROOT / "petrolab" / "dataset_visibility.py").exists()
assert (ROOT / "petrolab" / "table_views.py").exists()

selection_context = (UI / "selection_context.py").read_text(encoding="utf-8")
for marker in [
    "class SelectionContext", "class RowStates", '"replace"', '"add"', '"subtract"',
    '"hidden"', '"excluded"', "def set_selection(", "def set_row_state(",
]:
    assert marker in selection_context, marker
selection_components = (UI / "selection_components.py").read_text(encoding="utf-8")
for marker in [
    "def render_selection_panel(", "set_work_group", "clear_work_group", "assign_generation",
    "set_row_state", 'navigate("plots")', 'navigate("multi_panel")', 'navigate("statistics")',
    'navigate("grain_profile")', 'navigate("formulae")', "seed_selection_plot_handoff",
]:
    assert marker in selection_components, marker

# Airtable-like table controls are one canonical working surface. View controls
# must remain separate from the scientific linked Selection.
analysis_table = (UI / "analysis_table.py").read_text(encoding="utf-8")
field_presets = (UI / "field_presets.py").read_text(encoding="utf-8")
for marker in [
    "def render_analysis_table(", '"Выбрать"', "human_point_label", "set_selection", "Другой столбец…",
    'st.popover("Поля"', 'st.popover("Фильтр"', 'st.popover("Группа"', 'st.popover("Сортировка"',
    '"Все видимые"', '"Инвертировать"', "clear_selection", "Карточка точки", "render_record_detail",
    "list_table_views", "save_table_view",
]:
    assert marker in analysis_table, marker
for marker in ['"Основное"', '"Микрозонд"', '"Trace"', '"APFU"', '"QC"', '"Все"', '"Свои"']:
    assert marker in field_presets, marker
assert '"Химия": "Микрозонд"' in field_presets, "legacy chemistry views must migrate"
assert '"Расчёты": "APFU"' in field_presets, "legacy calculated views must migrate"
assert "_analysis_id" in analysis_table, "immutable ID must exist internally"

# JMP-like graph selection tools stay visible and write only through SelectionContext.
xy = (UI / "xy_components.py").read_text(encoding="utf-8")
for marker in [
    '"Точка"', '"Прямоугольник"', '"Лассо"', '"Панорама"',
    "render_selection_mode", "render_selection_panel", "set_selection",
    'key="petrolab_quick_interactive_plot"', 'key="petrolab_advanced_interactive_plot"',
    '"Confidence ellipse"', '"Convex hull"', '"KDE"',
]:
    assert marker in xy, marker
assert "set_work_group" not in xy, "Work Group persistence belongs to shared selection actions"
assert "assign_generation" not in xy, "Generation persistence belongs to shared selection actions"
assert "st.data_editor(pd.DataFrame(polygon" not in xy, "raw polygon-coordinate editor returned to normal UX"

plot_spec = (UI / "plot_spec.py").read_text(encoding="utf-8")
for marker in ["class PlotSpec", "dataset_ids", "analysis_ids", "group_column", "style_map", "send_to_multi_panel"]:
    assert marker in plot_spec, marker
smart_start = (UI / "smart_plot_start.py").read_text(encoding="utf-8")
for marker in [
    "resolve_plot_scope", "choose_xy_recommendation", "seed_xy_state",
    "seed_import_plot_handoff", "seed_selection_plot_handoff", "advanced_recipe_from_spec",
]:
    assert marker in smart_start, marker
plots = (PAGES / "plots_dashboard.py").read_text(encoding="utf-8")
for marker in [
    "resolve_plot_scope", "choose_xy_recommendation", "seed_xy_state", '"Smart Start ·',
    "PlotSpec(", "set_current_plot_spec", "send_to_multi_panel",
    '"＋ Добавить диаграмму"', '"Настроить подробнее"', "advanced_recipe_from_spec",
    "render_series_manager", "_plots_show_advanced",
]:
    assert marker in plots, marker
for obsolete_mode in ['"Быстрое построение"', '"Расширенный редактор"', '"Режим XY"']:
    assert obsolete_mode not in plots, f"up-front XY mode fork returned: {obsolete_mode}"
assert "st.tabs(" not in plots, "compact and deep XY must not both execute on every rerun"

# Origin-like managers own series visibility/order and the multi-panel layer list.
# Series rows can also explicitly feed the shared JMP SelectionContext.
plot_manager = (UI / "plot_manager.py").read_text(encoding="utf-8")
for marker in [
    "def render_series_manager(", '"Показывать"', '"В отбор"', '"Серия"', '"Порядок"',
    '"Заменить отбор"', '"Добавить"', '"Вычесть"', "set_selection",
]:
    assert marker in plot_manager, marker
panel_manager = (UI / "panel_manager.py").read_text(encoding="utf-8")
for marker in [
    "def render_panel_manager(", '"Панель"', '"X"', '"Y"', '"Название"', '"log X"', '"log Y"', '"Порядок"',
    '"Убрать"', '"Дублировать"', "_saved_source", "_inbox_token", "_panel_rows_after_actions",
]:
    assert marker in panel_manager, marker

multi = (PAGES / "multi_panel.py").read_text(encoding="utf-8")
for marker in [
    "peek_multi_panel_inbox", "render_linked_panel_selection", "render_selection_panel",
    '"Сравнить на нескольких диаграммах"', "render_panel_manager", "render_series_manager",
    "_SCOPE_IDS_KEY", '"Весь набор"',
]:
    assert marker in multi, marker
assert "def _ordered_panels(" not in multi, "vertical card/order workflow returned after Panel Manager consolidation"
linked = (UI / "linked_panels.py").read_text(encoding="utf-8")
for marker in ["read_selection", "set_selection", "read_row_states", "render_selection_mode"]:
    assert marker in linked, marker
assert "_linked_selection_ids" not in linked, "page-local linked selection state returned"

statistics = (PAGES / "statistics.py").read_text(encoding="utf-8")
for marker in [
    "read_row_states", "set_selection", "render_selection_panel",
    '"Показать эти кластеры на XY"', 'navigate("plots")',
]:
    assert marker in statistics, marker
assert "st.tabs(" not in statistics, "all statistics sections must not execute eagerly"

grain = (PAGES / "grain_profile.py").read_text(encoding="utf-8")
for marker in [
    '"В профиль"', '"Порядок"', "human_point_label", "st.data_editor(",
    "Сделать общим отбором", "set_selection",
]:
    assert marker in grain, marker
assert 'st.multiselect("Точки"' not in grain, "giant point multiselect returned"

formulae = (PAGES / "formulae.py").read_text(encoding="utf-8")
for marker in [
    "read_selection", '"Текущий отбор ·', "save_point_formula_results", "human_point_label",
]:
    assert marker in formulae, marker

generations = (PAGES / "generations.py").read_text(encoding="utf-8")
for marker in ["human_point_label", '"Выбрать"', "st.data_editor(", "_project_work_group_map"]:
    assert marker in generations, marker
assert "aid[:10]" not in generations and "analysis_id[:" not in generations

home = (PAGES / "home_dashboard.py").read_text(encoding="utf-8")
for marker in ["home_recent_datasets_table", 'selection_mode="single-row"', "_open_dataset", "visible_working_datasets"]:
    assert marker in home, marker
workspace = (PAGES / "object_workspace.py").read_text(encoding="utf-8")
assert "render_analysis_table" in workspace
assert "st.tabs(" not in workspace, "Workspace sections must render conditionally"

# Primary navigation is the product model; implementation routes stay addressable
# but hidden from the normal sidebar.
from petrolab.ui.navigation import PRIMARY_NAV, ROUTE_LABELS
expected_primary = [
    ("home", "Главная"),
    ("workspace", "Данные"),
    ("plots", "Графики"),
    ("statistics", "Статистика"),
    ("thin_section", "Шлифы и изображения"),
    ("calculate", "Расчёты"),
    ("publish", "Публикация"),
    ("search", "Поиск"),
    ("settings", "Настройки"),
]
assert PRIMARY_NAV == expected_primary, PRIMARY_NAV
for route in ["formulae", "minerals", "quick_import", "sources", "database", "multi_panel", "grain_profile"]:
    assert route in ROUTE_LABELS, f"compatibility route disappeared: {route}"
    assert route not in {item[0] for item in PRIMARY_NAV}, f"implementation route leaked into primary nav: {route}"
assert "def go_back(" in NAVIGATION and "push_current" in NAVIGATION

# Canonical renderers must no longer be rebound through the old UI wrapper stack.
for marker in [
    "from .add_data import render_add_data_page",
    "from .home_dashboard import render_home_dashboard_page as render_home_page",
    "from .object_workspace import render_object_workspace_page",
    "from .plots_dashboard import render_plots_dashboard_page as render_plots_page",
    "from .multi_panel import render_multi_panel_page",
]:
    assert marker in PAGES_INIT, marker
for forbidden in [
    "render_add_data_page_v0154_bridge as render_add_data_page",
    "from .v0151_intake_wrappers import render_add_data_page",
    "render_multi_panel_page_v0154_bridge as render_multi_panel_page",
    "render_plots_page_v0154_bridge as render_plots_page",
]:
    assert forbidden not in PAGES_INIT, forbidden
legacy_intake = (PAGES / "v0151_intake_wrappers.py").read_text(encoding="utf-8")
for forbidden in [
    "_universal._file_token =", "_extensions._batch_token =",
    "_universal._render_table_import =", "_universal._render_image_wizard =",
]:
    assert forbidden not in legacy_intake, forbidden

# Global project context remains sidebar-owned.
project_context = (UI / "project_context.py").read_text(encoding="utf-8")
for marker in ["ACTIVE_PROJECT_KEY", "def active_project(", "def active_project_id(", "def set_active_project("]:
    assert marker in project_context, marker
assert "render_sidebar" in APP and "PAGE_GROUPS" not in APP

# Source visibility is explicitly graph-local and non-destructive.
source_controls = (UI / "source_controls.py").read_text(encoding="utf-8")
for marker in [
    "Статьи и источники на графике", "Включить все", "только на текущий график",
    "данные остаются в базе", "filter_visible_sources",
]:
    assert marker in source_controls, marker

# Destructive actions remain explicit and reusable.
destructive = (UI / "destructive_actions.py").read_text(encoding="utf-8")
for marker in ["def confirm_then(", "def render_pending(", "_pending_destructive_"]:
    assert marker in destructive, marker

# High-value pages keep the shared visual hierarchy.
for page_name in [
    "add_data.py", "home_dashboard.py", "sources_dashboard.py", "analyses_dashboard.py",
    "plots_dashboard.py", "images_dashboard.py", "settings.py", "statistics.py",
    "formulae.py", "help.py", "rocks.py", "science_plots.py", "object_workspace.py",
    "multi_panel.py", "grain_profile.py",
]:
    path = PAGES / page_name
    assert path.exists(), page_name
    text = path.read_text(encoding="utf-8")
    assert "render_page_header" in text, f"dashboard page lacks shared header: {page_name}"

for path in sorted(PAGES.glob("*.py")):
    text = path.read_text(encoding="utf-8")
    assert "use_container_width" not in text, f"deprecated width API in {path.name}"
    for match in re.finditer(r"width\s*=\s*(\d+)", text):
        width = int(match.group(1))
        assert width <= 1600, f"suspicious fixed width {width}px in {path.name}"

print("v0.15.8 Airtable/JMP/Origin + Smart Start UI structure tests: OK")