from __future__ import annotations

import unittest

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import pandas as pd

from petrolab.group_styles import DEFAULT_GROUP_COLORS, MISSING_GROUP_LABEL, display_group_series
from petrolab.interactive_plotting import build_interactive_scatter
from petrolab.plotting import build_scatter


class GroupStyleConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.df = pd.DataFrame({
            "x": [1.0, 2.0, 3.0, 4.0],
            "y": [2.0, 3.0, 4.0, 5.0],
            "group": ["A", "B", None, ""],
            "_analysis_id": ["a1", "a2", "a3", "a4"],
        })

    def test_missing_group_label_is_stable(self):
        labels = display_group_series(self.df["group"]).tolist()
        self.assertEqual(labels, ["A", "B", MISSING_GROUP_LABEL, MISSING_GROUP_LABEL])

    def test_interactive_and_publication_defaults_match(self):
        plotly_fig = build_interactive_scatter(self.df, "x", "y", "group")
        plotly_traces = [trace for trace in plotly_fig.data if getattr(trace, "mode", "") == "markers"]
        plotly_labels = [trace.name for trace in plotly_traces]
        plotly_colors = [trace.marker.color for trace in plotly_traces]

        mpl_fig = build_scatter(self.df, "x", "y", group="group")
        ax = mpl_fig.axes[0]
        handles, labels = ax.get_legend_handles_labels()
        facecolors = []
        for handle in handles:
            rgba = handle.get_facecolor()
            if len(rgba):
                facecolors.append(mcolors.to_hex(rgba[0], keep_alpha=False).upper())
        plt.close(mpl_fig)

        self.assertEqual(plotly_labels, ["A", "B", MISSING_GROUP_LABEL])
        self.assertEqual(labels, plotly_labels)
        self.assertEqual([str(c).upper() for c in plotly_colors], list(DEFAULT_GROUP_COLORS[:3]))
        self.assertEqual(facecolors, list(DEFAULT_GROUP_COLORS[:3]))

    def test_user_style_overrides_default_in_both_renderers(self):
        styles = {"A": {"color": "#123456"}}
        plotly_fig = build_interactive_scatter(self.df.iloc[:2], "x", "y", "group", style_map=styles)
        self.assertEqual(str(plotly_fig.data[0].marker.color).upper(), "#123456")
        mpl_fig = build_scatter(self.df.iloc[:2], "x", "y", group="group", style_map=styles)
        first = mpl_fig.axes[0].collections[0].get_facecolor()[0]
        self.assertEqual(mcolors.to_hex(first, keep_alpha=False).upper(), "#123456")
        plt.close(mpl_fig)


if __name__ == "__main__":
    unittest.main()
