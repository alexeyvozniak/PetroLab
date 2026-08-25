from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent
THEME = (ROOT / "petrolab" / "ui" / "theme.py").read_text(encoding="utf-8")
LAYOUT = (ROOT / "petrolab" / "ui" / "layout.py").read_text(encoding="utf-8")
NAVIGATION = (ROOT / "petrolab" / "ui" / "navigation.py").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")
REFERENCE_SELECTION = (ROOT / "petrolab" / "ui" / "reference_selection.py").read_text(encoding="utf-8")
REFERENCE_PAGES = {
    name: (ROOT / "petrolab" / "ui" / "pages" / name).read_text(encoding="utf-8")
    for name in (
        "add_data_reference.py",
        "linked_views_reference.py",
        "search_reference.py",
        "slides_reference.py",
        "analyses_dashboard.py",
    )
}

# Final selected Product Design reference: a white scientific workspace, compact
# light rail, thin separators, dense tables and restrained teal actions.
for marker in [
    'font-family: "Segoe UI", Inter, Arial, sans-serif',
    '--petro-bg: #ffffff',
    '--petro-sidebar: #ffffff',
    '--petro-accent: #0b7f7a',
    '--petro-radius-sm: 5px',
    '--petro-radius-md: 7px',
    '--petro-border-strong',
    '[data-testid="stDataFrame"]',
    '[data-testid="stTabs"] [data-baseweb="tab-list"]',
    'border-left:3px solid var(--petro-accent)',
    '.pd-status-strip',
    '.pd-chip',
    '.petrolab-selection-tray',
]:
    assert marker in THEME, marker

# Primary rail order is intentional and mirrors the supplied screenshot.
ordered = [
    '("home", "Обзор")',
    '("projects", "Проекты")',
    '("search", "Поиск")',
    '("samples", "Образцы")',
    '("slides", "Шлифы")',
    '("analyses", "Анализы")',
    '("linked_views", "Построение")',
    '("add_data", "Добавить")',
]
positions = []
for marker in ordered:
    assert marker in NAVIGATION, marker
    positions.append(NAVIGATION.index(marker))
assert positions == sorted(positions)

# Key product surfaces should use the screenshot-led implementations. Parse every
# source so lazy loading cannot hide syntax errors until a user opens the route.
for filename, source in REFERENCE_PAGES.items():
    ast.parse(source, filename=filename)
ast.parse(REFERENCE_SELECTION, filename="reference_selection.py")

for marker in [
    'add_data_reference',
    'linked_views_reference',
    'search_reference',
    'slides_reference',
]:
    assert marker in APP, marker

for filename, markers in {
    "linked_views_reference.py": ["Предварительный отбор", "Кодировка", "Сохранить как рабочую группу"],
    "search_reference.py": ["Результаты", "Источники в выборке", "render_manual_selection_table"],
    "slides_reference.py": ["Связанный шлиф", "render_manual_selection_table", "render_selection_action_bar"],
    "analyses_dashboard.py": ["render_manual_selection_table", "render_selection_action_bar", "Редактирование"],
    "add_data_reference.py": ["Проверка импорта", "Сохранение", "render_intake_workflow"],
}.items():
    for marker in markers:
        assert marker in REFERENCE_PAGES[filename], f"{filename}: {marker}"

# Manual row selection is one cross-screen Selection, not per-table local state.
for marker in [
    '"Выбрать все видимые"', '"Снять видимые"', "read_selection", "set_selection",
    "set_work_group", 'navigate("linked_views")', 'navigate("slides")', 'navigate("statistics")',
]:
    assert marker in REFERENCE_SELECTION, marker

# Optional prose remains discoverable without occupying the workspace permanently.
for marker in [
    'class="petrolab-page-title-row"',
    'petrolab-page-help',
    'petrolab-section-help',
    'petrolab-inline-help',
    'aria-label="Подробнее"',
]:
    assert marker in LAYOUT, marker

assert "st.caption(text)" not in LAYOUT, "render_hint must not print long guidance inline"
assert "render_danger_intro" in LAYOUT, "safety-critical guidance remains explicit"

print("desktop application UI regression: OK")