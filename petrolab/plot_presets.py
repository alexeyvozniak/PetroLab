from __future__ import annotations

from typing import Final

from petrolab.visualization_presets import FIGURE_PRESETS


def _legacy_view(name: str) -> dict[str, object]:
    preset = FIGURE_PRESETS[name]
    return {
        "figure_width": preset.width_in,
        "figure_height": preset.height_in,
        "font_family": preset.font_family,
        "font_size": preset.font_size,
        "tick_size": preset.tick_size,
        "label_size": preset.label_size,
        "spine_width": preset.spine_width,
        "marker_size": preset.marker_size,
        "monochrome": preset.monochrome,
        "show_grid": preset.grid,
        "show_legend": True,
        "dpi": preset.dpi,
    }


JOURNAL_PRESETS: Final[dict[str, dict[str, object]]] = {
    "Свой": _legacy_view("Custom"),
    "Lithos": _legacy_view("Lithos"),
    "Geodynamics & Tectonophysics": _legacy_view("Geodynamics & Tectonophysics"),
    "ДАН": _legacy_view("ДАН"),
    "Elsevier · 1 колонка": _legacy_view("Elsevier 1-column"),
    "Elsevier · 2 колонки": _legacy_view("Elsevier 2-column"),
    "Supplementary": _legacy_view("Supplementary"),
}
