from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
THEME = (ROOT / "petrolab" / "ui" / "theme.py").read_text(encoding="utf-8")
APP = (ROOT / "app.py").read_text(encoding="utf-8")
PAGES = ROOT / "petrolab" / "ui" / "pages"

assert "@media (max-width: 900px)" in THEME
assert "overflow-x: auto" in THEME
assert "max-width" in THEME
assert "PAGE_GROUPS" in APP
assert "Работа с данными" in APP and "Графики и статистика" in APP and "Публикация" in APP

for path in sorted(PAGES.glob("*.py")):
    text = path.read_text(encoding="utf-8")
    assert "use_container_width" not in text, f"deprecated width API in {path.name}"
    # Prevent accidental giant fixed-width Streamlit elements in new/refactored pages.
    for match in re.finditer(r"width\s*=\s*(\d+)", text):
        width = int(match.group(1))
        assert width <= 700, f"fixed width {width}px in {path.name}; prefer width='stretch'"

for page_name in ["science_plots.py", "statistics.py", "rocks.py", "article_tables.py", "settings.py", "help.py", "updates.py"]:
    path = PAGES / page_name
    assert path.exists(), page_name
    text = path.read_text(encoding="utf-8")
    assert "st.title(" in text, f"page lacks a visible title: {page_name}"

print("UI layout structure tests: OK")
