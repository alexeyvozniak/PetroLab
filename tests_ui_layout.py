from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UI = ROOT / "petrolab" / "ui"
PAGES = UI / "pages"
THEME = (UI / "theme.py").read_text(encoding="utf-8")
LAYOUT = (UI / "layout.py").read_text(encoding="utf-8")
NAVIGATION = (UI / "navigation.py").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")

# Scientific-dashboard visual system and responsive behavior.
for token in ["--petro-bg", "--petro-surface", "--petro-text", "--petro-accent", "--petro-success", "--petro-warning", "--petro-danger"]:
    assert token in THEME, token
assert "focus-visible" in THEME
assert "@media (max-width: 1100px)" in THEME
assert "@media (max-width: 760px)" in THEME
assert "overflow-x: auto" in THEME
assert "max-width" in THEME
assert "render_page_header" in LAYOUT and "render_badges" in LAYOUT

# Navigation is flat/grouped: no second-stage workspace selector.
assert "render_sidebar" in APP
assert "PAGE_GROUPS" not in APP
assert "Рабочая область" not in APP
for label in ["Данные", "Исследование", "Материалы", "Публикация", "Система"]:
    assert label in NAVIGATION
for label in ["Главная", "Импорт", "База анализов", "Расчёты", "XY-диаграммы", "Изображения", "История правок данных"]:
    assert label in NAVIGATION

# High-value dashboard pages use the shared visual hierarchy.
for page_name in [
    "home_dashboard.py", "sources_dashboard.py", "analyses_dashboard.py",
    "plots_dashboard.py", "images_dashboard.py", "settings.py", "statistics.py",
    "formulae.py", "help.py",
]:
    path = PAGES / page_name
    assert path.exists(), page_name
    text = path.read_text(encoding="utf-8")
    assert "render_page_header" in text, f"dashboard page lacks shared header: {page_name}"

settings = (PAGES / "settings.py").read_text(encoding="utf-8")
assert 'st.tabs(' in settings
assert '"Интерфейс"' in settings and '"Рисунки"' in settings and '"Таблицы"' in settings and '"Анализ"' in settings
images = (PAGES / "images_dashboard.py").read_text(encoding="utf-8")
assert "st.columns([1.35, 1])" in images
assert "confirm_delete_image_" in images
plots = (PAGES / "plots_dashboard.py").read_text(encoding="utf-8")
assert '"Быстрое построение"' in plots and '"Расширенный редактор"' in plots
analyses = (PAGES / "analyses_dashboard.py").read_text(encoding="utf-8")
for view in ["Основное", "Химия", "Расчёты", "QC", "Все"]:
    assert view in analyses

for path in sorted(PAGES.glob("*.py")):
    text = path.read_text(encoding="utf-8")
    assert "use_container_width" not in text, f"deprecated width API in {path.name}"
    for match in re.finditer(r"width\s*=\s*(\d+)", text):
        width = int(match.group(1))
        assert width <= 1600, f"suspicious fixed width {width}px in {path.name}"

print("UI dashboard structure tests: OK")
