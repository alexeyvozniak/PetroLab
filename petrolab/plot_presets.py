from __future__ import annotations

from typing import Final


JOURNAL_PRESETS: Final[dict[str, dict[str, float | bool]]] = {
    "Свой": {
        "figure_width": 7.8,
        "figure_height": 5.8,
        "font_size": 10,
        "tick_size": 9,
        "spine_width": 1.0,
        "marker_size": 58,
        "monochrome": False,
        "show_grid": False,
        "show_legend": True,
    },
    "Lithos": {
        "figure_width": 7.2,
        "figure_height": 5.4,
        "font_size": 10,
        "tick_size": 9,
        "spine_width": 1.0,
        "marker_size": 60,
        "monochrome": False,
        "show_grid": False,
        "show_legend": True,
    },
    "Geodynamics & Tectonophysics": {
        "figure_width": 7.0,
        "figure_height": 5.3,
        "font_size": 10,
        "tick_size": 9,
        "spine_width": 1.0,
        "marker_size": 64,
        "monochrome": False,
        "show_grid": False,
        "show_legend": True,
    },
    "ДАН": {
        "figure_width": 6.7,
        "figure_height": 5.0,
        "font_size": 9,
        "tick_size": 8,
        "spine_width": 1.1,
        "marker_size": 68,
        "monochrome": True,
        "show_grid": False,
        "show_legend": True,
    },
    "Supplementary": {
        "figure_width": 7.5,
        "figure_height": 5.8,
        "font_size": 10,
        "tick_size": 9,
        "spine_width": 1.0,
        "marker_size": 54,
        "monochrome": False,
        "show_grid": True,
        "show_legend": True,
    },
}
