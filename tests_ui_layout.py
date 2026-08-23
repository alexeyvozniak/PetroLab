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

# Approved reference visual system: light scientific workspace, restrained teal
# actions and a narrow dark rail on analysis-first screens.
for token in [
    "--petro-bg: #f6f8fa", "--petro-surface: #ffffff", "--petro-sidebar: #10283a",
    "--petro-text: #162033", "--petro-text-muted: #68758a", "--petro-accent: #0f7f82",
    "--petro-success", "--petro-warning", "--petro-danger", ".pd-status-strip", ".pd-chip",
    "focus-visible", "@media (max-width:1100px)", "@media (max-width:760px)", "overflow-x:auto",
]:
    assert token in THEME, token
assert '<h1 class="petrolab-page-title">' in LAYOUT
assert '<h2 class="petrolab-section-title">' in LAYOUT
assert "render_page_header" in LAYOUT and "render_badges" in LAYOUT

# One global project context remains authoritative.
for marker in ["ACTIVE_PROJECT_KEY", "def active_project(", "def active_project_id(", "def set_active_project("]:
    assert marker in PROJECT_CONTEXT, marker
assert "active_project_id" in NAVIGATION and "set_active_project" in NAVIGATION

# The primary rail mirrors the supplied Product Design references.
for marker in [
    '("home", "Обзор")', '("projects", "Проекты")', '("samples", "Образцы")',
    '("search", "Поиск")', '("slides", "Шлифы")', '("analyses", "Анализы")',
    '("linked_views", "Построение")', '("add_data", "Добавить")', '"Ещё"', '"Настройки"',
]:
    assert marker in NAVIGATION, marker

# Reference-led screens are first-class routes and must parse even though app.py
# imports them lazily for faster startup.
reference_pages = {
    "add_data_reference.py": ["Проверка импорта", "render_intake_workflow"],
    "linked_views_reference.py": ["Предварительный отбор", "Кодировка", "Сохранить как рабочую группу"],
    "search_reference.py": ["Результаты", "Источники в выборке", "Построить график по выборке"],
    "slides_reference.py": ["Фотографии", "Связанный шлиф", "Выбрано:"],
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
    '"linked_views": ("petrolab.ui.pages.linked_views_reference", "render_linked_views_reference_page")',
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
