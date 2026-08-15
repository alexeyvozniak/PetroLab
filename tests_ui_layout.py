from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAGES = ROOT / "petrolab" / "ui" / "pages"
NAVIGATION = (ROOT / "petrolab" / "ui" / "navigation.py").read_text(encoding="utf-8")
THEME = (ROOT / "petrolab" / "ui" / "theme.py").read_text(encoding="utf-8")
LAYOUT = (ROOT / "petrolab" / "ui" / "layout.py").read_text(encoding="utf-8")
DESTRUCTIVE_ACTIONS = (ROOT / "petrolab" / "ui" / "destructive_actions.py").read_text(encoding="utf-8")

assert "use_container_width" not in NAVIGATION
assert "use_container_width" not in THEME
assert "use_container_width" not in LAYOUT
assert "st.set_page_config" not in LAYOUT
assert "st.set_page_config" not in NAVIGATION

# Sidebar is task-first and advanced tools stay grouped.
for marker in ["DAILY_NAV", "TOOL_SECTIONS", 'with st.expander("Все инструменты"']:
    assert marker in NAVIGATION, marker
for label in ["Главная", "Рабочий стол", "Работать со шлифом", "Добавить данные", "Вся база", "XY-диаграммы"]:
    assert label in NAVIGATION, label
assert "list_accessible_datasets" in NAVIGATION
assert "list_datasets(" not in NAVIGATION

# Responsive theme contract.
for marker in [
    "@media (max-width: 1100px)",
    "@media (max-width: 760px)",
    ".block-container",
    "overflow-wrap: anywhere",
]:
    assert marker in THEME, marker

# Shared page chrome stays reusable rather than copied across pages.
for marker in ["def render_page_header(", "def render_section_header(", "def render_badges("]:
    assert marker in LAYOUT, marker

# Daily pages use the shared header rather than raw page titles.
for filename in [
    "home_dashboard.py",
    "object_workspace.py",
    "thin_section_workspace.py",
    "add_data.py",
    "database_browser.py",
    "plots_dashboard.py",
    "article_tables.py",
    "attention.py",
]:
    text = (PAGES / filename).read_text(encoding="utf-8")
    assert "render_page_header(" in text, filename

# Long form pages must retain explicit tabs/sections rather than one endless form.
for filename in ["settings.py", "plots_dashboard.py", "rocks.py"]:
    text = (PAGES / filename).read_text(encoding="utf-8")
    assert "st.tabs(" in text, filename

# Main dashboards must avoid fixed-width UI APIs and keep stable task routing.
home = (PAGES / "home_dashboard.py").read_text(encoding="utf-8")
assert "def _action(" not in home
assert home.count('key=f"home_{route}"') == 1

# Plot settings and presets remain wired through the quick and advanced workflow.
plots = (PAGES / "plots_dashboard.py").read_text(encoding="utf-8")
settings = (PAGES / "settings.py").read_text(encoding="utf-8")
assert 'st.tabs(' in settings
assert '"Интерфейс"' in settings and '"Рисунки"' in settings and '"Таблицы"' in settings and '"Анализ"' in settings
assert '"Быстрое построение"' in plots and '"Расширенный редактор"' in plots
assert "FIGURE_PRESETS" in plots
for marker in ["preset.width_in", "preset.height_in", "preset.font_family", "preset.font_size", "preset.tick_size", "preset.spine_width", "preset.dpi"]:
    assert marker in plots, f"Quick XY does not apply configured preset field: {marker}"
assert 'f"{preset.title}' in plots

# Destructive actions are explicit and reusable, never installed dynamically.
for marker in ["def confirm_then(", "def render_pending(", "_pending_destructive_"]:
    assert marker in DESTRUCTIVE_ACTIONS, marker
rocks = (PAGES / "rocks.py").read_text(encoding="utf-8")
for marker in [
    'action_key = f"rock_links_{rock_id}"', "confirm_then(action_key", "confirm_then(\"rock_image\"",
    "render_pending(", "set_mineral_links as _set_mineral_links", "delete_rock_image as _delete_rock_image",
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
