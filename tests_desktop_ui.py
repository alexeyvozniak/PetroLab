from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
THEME = (ROOT / "petrolab" / "ui" / "theme.py").read_text(encoding="utf-8")
LAYOUT = (ROOT / "petrolab" / "ui" / "layout.py").read_text(encoding="utf-8")
NAVIGATION = (ROOT / "petrolab" / "ui" / "navigation.py").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")

# Approved Product Design direction: a light scientific workspace, compact controls,
# teal actions and a narrow dark navigation rail on the analysis-first screens.
for marker in [
    'font-family: "Segoe UI", Inter, Arial, sans-serif',
    '--petro-bg: #f6f8fa',
    '--petro-sidebar: #10283a',
    '--petro-accent: #0f7f82',
    '--petro-radius-sm: 6px',
    '--petro-radius-md: 8px',
    '--petro-border-strong',
    '[data-testid="stDataFrame"]',
    '[data-testid="stTabs"] [data-baseweb="tab-list"]',
    'border-left:3px solid #18b6b2',
    '.pd-status-strip',
    '.pd-chip',
]:
    assert marker in THEME, marker

# Primary rail must match the short task-oriented navigation shown in the references.
for marker in [
    '("home", "Обзор")',
    '("projects", "Проекты")',
    '("samples", "Образцы")',
    '("search", "Поиск")',
    '("slides", "Шлифы")',
    '("analyses", "Анализы")',
    '("linked_views", "Построение")',
    '("add_data", "Добавить")',
]:
    assert marker in NAVIGATION, marker

# Key product surfaces should use the reference-led implementations, not the old
# generic Streamlit page layouts.
for marker in [
    'add_data_reference',
    'linked_views_reference',
    'search_reference',
    'slides_reference',
]:
    assert marker in APP, marker

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
