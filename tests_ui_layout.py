from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "petrolab" / "ui"
PAGES = UI / "pages"
THEME = (UI / "theme.py").read_text(encoding="utf-8")
LAYOUT = (UI / "layout.py").read_text(encoding="utf-8")
NAVIGATION = (UI / "navigation.py").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")
PROJECT_CONTEXT = (UI / "project_context.py").read_text(encoding="utf-8")
DESTRUCTIVE_ACTIONS = (UI / "destructive_actions.py").read_text(encoding="utf-8")
SCIENCE = (PAGES / "science_plots.py").read_text(encoding="utf-8")
REFERENCE_SELECTION = (UI / "reference_selection.py").read_text(encoding="utf-8")

# Approved final visual target: white scientific workspace, light compact rail,
# restrained teal actions, thin dividers and dense data tables.
for token in [
    "--petro-bg: #ffffff", "--petro-surface: #ffffff", "--petro-sidebar: #ffffff",
    "--petro-text: #172230", "--petro-text-muted: #6c7886", "--petro-accent: #0b7f7a",
    "--petro-success", "--petro-warning", "--petro-danger", ".pd-status-strip", ".pd-chip",
    ".petrolab-selection-tray", "focus-visible", "@media (max-width:1100px)",
    "@media (max-width:760px)", "overflow-x:auto",
]:
    assert token in THEME, token
assert '<h1 class="petrolab-page-title">' in LAYOUT
assert '<h2 class="petrolab-section-title">' in LAYOUT
assert "render_page_header" in LAYOUT and "render_badges" in LAYOUT

# One global project context remains authoritative.
for marker in ["ACTIVE_PROJECT_KEY", "def active_project(", "def active_project_id(", "def set_active_project("]:
    assert marker in PROJECT_CONTEXT, marker
assert "active_project_id" in NAVIGATION and "set_active_project" in NAVIGATION

# The primary rail follows the selected screenshot order.
ordered_markers = [
    '("home", "Обзор")', '("projects", "Проекты")', '("search", "Поиск")',
    '("samples", "Образцы")', '("slides", "Шлифы")', '("analyses", "Анализы")',
    '("linked_views", "Построение")', '("add_data", "Добавить")',
]
positions = []
for marker in ordered_markers:
    assert marker in NAVIGATION, marker
    positions.append(NAVIGATION.index(marker))
assert positions == sorted(positions), "primary navigation order drifted from reference"
assert '"Ещё"' in NAVIGATION and '"Настройки"' in NAVIGATION

# Manual table selection is a single shared primitive, not one-off checkbox code.
for marker in [
    "def render_manual_selection_table(", "def render_selection_action_bar(",
    '"Выбрать все видимые"', '"Снять видимые"', "set_selection", "set_work_group",
    'navigate("linked_views")', 'navigate("slides")', 'navigate("statistics")',
]:
    assert marker in REFERENCE_SELECTION, marker

# Reference-led screens are first-class routes and use the shared Selection.
reference_pages = {
    "add_data_reference.py": ["Проверка импорта", "render_intake_workflow"],
    "linked_views_reference.py": ["Предварительный отбор", "Кодировка", "Сохранить как рабочую группу"],
    "linked_views_compat.py": ["_scatter_compatible", "render_linked_views_reference_page"],
    "search_reference.py": ["Результаты", "Источники в выборке", "render_manual_selection_table", "render_selection_action_bar"],
    "slides_reference.py": ["Связанный шлиф", "render_manual_selection_table", "render_selection_action_bar"],
    "analyses_dashboard.py": ["render_manual_selection_table", "render_selection_action_bar", "Редактирование"],
}
for filename, markers in reference_pages.items():
    path = PAGES / filename
    assert path.exists(), filename
    source = path.read_text(encoding="utf-8")
    ast.parse(source, filename=filename)
    for marker in markers:
        assert marker in source, f"{filename}: {marker}"

for marker in [
    '"add_data": ("petrolab.ui.pages.add_data_reference", "render_add_data_reference_page")',
    '"linked_views": ("petrolab.ui.pages.linked_views_compat", "render_linked_views_reference_page")',
    '"search": ("petrolab.ui.pages.search_reference", "render_search_reference_page")',
    '"slides": ("petrolab.ui.pages.slides_reference", "render_slides_reference_page")',
    "def _resolve_renderer(", "import_module(module_path)",
]:
    assert marker in APP, marker

# Core dashboard owners still exist; no runtime monkeypatch policy layer returns.
for page_name in [
    "home_dashboard.py", "sources_dashboard.py", "analyses_dashboard.py", "plots_dashboard.py",
    "images_dashboard.py", "settings.py", "statistics.py", "formulae.py", "rocks.py", "science_plots.py",
]:
    assert (PAGES / page_name).exists(), page_name
for obsolete in [
    UI / "import_page_policy.py", UI / "plot_page_policy.py", UI / "image_page_policy.py",
    UI / "science_page_policy.py", UI / "destructive_page_policy.py",
]:
    assert not obsolete.exists(), f"obsolete UI layer returned: {obsolete.name}"
assert not list(UI.glob("*_page_policy.py")), "runtime page policy module returned"

# Safety-critical domain rules remain separate from visual redesign.
for marker in ["def confirm_then(", "def render_pending(", "_pending_destructive_"]:
    assert marker in DESTRUCTIVE_ACTIONS, marker
for marker in [
    "def _mineral_filtered_presets(", "require_known_units=True", "_PATTERN_YLABELS",
    "def _apply_pattern_group_styles(", "matches_preset", "Grouped boxplot требует ровно один числовой параметр",
]:
    assert marker in SCIENCE, marker

# Keep deprecated Streamlit width API and suspicious oversized fixed widths out of pages.
for path in sorted(PAGES.glob("*.py")):
    text = path.read_text(encoding="utf-8")
    assert "use_container_width" not in text, f"deprecated width API in {path.name}"
    for match in re.finditer(r"width\s*=\s*(\d+)", text):
        assert int(match.group(1)) <= 1600, f"suspicious fixed width {match.group(1)}px in {path.name}"

print("UI Product Design structure tests: OK")
