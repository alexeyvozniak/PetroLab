from __future__ import annotations

import unittest

import matplotlib.pyplot as plt
import pandas as pd

from petrolab.interactive_plotting import build_interactive_scatter
from petrolab.plotting import build_scatter


class ManualFieldTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({
            "_analysis_id": ["a", "b", "c", "d"],
            "Generation": ["G1"] * 4,
            "X": [0.0, 1.0, 1.0, 0.0],
            "Y": [0.0, 0.0, 1.0, 1.0],
        })
        self.manual = [[-0.1, -0.1], [1.2, -0.1], [1.1, 1.2], [-0.2, 1.1]]
        self.styles = {
            "G1": {
                "display_mode": "field",
                "color": "#336699",
                "envelope_method": "confidence_ellipse",
                "envelope_level": 0.90,
                "manual_envelope_points": self.manual,
                "envelope_geometry_status": "manual",
                "envelope_fill": True,
                "envelope_fill_color": "#ff0000",
                "envelope_alpha": 0.25,
                "envelope_line_color": "#000000",
                "envelope_line_width": 2.5,
                "envelope_line_dash": "dash",
            }
        }

    def test_interactive_manual_field_uses_manual_geometry_and_style(self):
        fig = build_interactive_scatter(self.frame, "X", "Y", "Generation", style_map=self.styles)
        self.assertEqual(len(fig.data), 1)
        trace = fig.data[0]
        self.assertEqual(list(trace.x)[:4], [-0.1, 1.2, 1.1, -0.2])
        self.assertEqual(trace.fill, "toself")
        self.assertIn("rgba(255,0,0,0.250)", trace.fillcolor)
        self.assertEqual(trace.line.color, "#000000")
        self.assertEqual(trace.line.width, 2.5)
        self.assertEqual(trace.line.dash, "dash")
        self.assertIn("manual", trace.hovertemplate)
        self.assertIn("исходное: confidence_ellipse", trace.hovertemplate)

    def test_publication_export_uses_manual_geometry(self):
        fig = build_scatter(self.frame, "X", "Y", "Generation", style_map=self.styles)
        try:
            ax = fig.axes[0]
            self.assertGreaterEqual(len(ax.patches), 1)
            self.assertGreaterEqual(len(ax.lines), 2)  # visible contour + invisible legend handle
            contour = ax.lines[0]
            self.assertAlmostEqual(float(contour.get_xdata()[0]), -0.1)
            self.assertAlmostEqual(float(contour.get_ydata()[0]), -0.1)
            self.assertEqual(contour.get_color(), "#000000")
            self.assertEqual(contour.get_linestyle(), "--")
        finally:
            plt.close(fig)


if __name__ == "__main__":
    unittest.main()
