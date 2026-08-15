from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
THEME = (ROOT / "petrolab" / "ui" / "theme.py").read_text(encoding="utf-8")
LAYOUT = (ROOT / "petrolab" / "ui" / "layout.py").read_text(encoding="utf-8")

# PetroLab should read as a dense scientific desktop application, not a soft web dashboard.
for marker in [
    'font-family: "Segoe UI", Arial, sans-serif',
    '--petro-radius-sm: 4px',
    '--petro-radius-md: 6px',
    '--petro-border-strong',
    '[data-testid="stDataFrame"]',
    '[data-testid="stTabs"] [data-baseweb="tab-list"]',
    'border-left: 3px solid var(--petro-accent)',
]:
    assert marker in THEME, marker

# Optional prose must be discoverable without occupying the workspace permanently.
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
