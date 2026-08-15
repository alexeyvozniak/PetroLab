from __future__ import annotations

import unittest

import pandas as pd

from petrolab.rock_work_groups import rock_selection_id
from petrolab.ui.linked_panels import build_linked_panel_figure, selection_ids_from_event
from petrolab.ui.pages.multi_panel import _panel_defaults


class LinkedSelectionEventTests(unittest.TestCase):
    def test_single_click_returns_one_stable_id(self) -> None:
        event = {"selection": {"points": [{"customdata": ["analysis-b"]}]}}
        self.assertEqual(selection_ids_from_event(event), ["analysis-b"])

    def test_box_or_lasso_returns_exact_current_ids(self) -> None:
        event = {
            "selection": {
                "points": [
                    {"customdata": ["a"]},
                    {"customdata": ["c"]},
                    {"customdata": ["a"]},
                ]
            }
        }
        self.assertEqual(selection_ids_from_event(event), ["a", "c"])

    def test_explicit_empty_selection_clears_selection(self) -> None:
        self.assertEqual(selection_ids_from_event({"selection": {"points": []}}), [])
        self.assertIsNone(selection_ids_from_event(None))


class LinkedTenPanelTests(unittest.TestCase):
    def test_same_selected_id_is_highlighted_on_all_ten_panels(self) -> None:
        frame = pd.DataFrame({
            "_analysis_id": ["a", "b", "c"],
            "x": [1.0, 2.0, 3.0],
            **{f"y{i}": [10.0 + i, 20.0 + i, 30.0 + i] for i in range(10)},
        })
        panels = [
            {"x": "x", "y": f"y{i}", "title": f"P{i + 1}", "log_x": False, "log_y": False}
            for i in range(10)
        ]
        figure = build_linked_panel_figure(
            frame,
            panels,
            id_column="_analysis_id",
            selected_ids=["b"],
            columns=3,
        )
        self.assertEqual(len(figure.data), 10)
        for trace in figure.data:
            self.assertEqual(list(trace.selectedpoints), [1])

    def test_panel_defaults_can_fill_up_to_ten_pairs(self) -> None:
        numeric = ["SiO2", "TiO2", "Al2O3", "MgO", "FeOt", "CaO", "Na2O", "K2O", "Rb", "Sr", "Nb"]
        pairs = _panel_defaults(numeric)
        self.assertLessEqual(len(pairs), 10)
        self.assertGreaterEqual(len(pairs), 6)
        self.assertEqual(len(pairs), len(set(pairs)))


class WholeRockSelectionIdentityTests(unittest.TestCase):
    def test_determinations_of_same_sample_remain_distinct(self) -> None:
        self.assertEqual(rock_selection_id(19, 101), "d:101")
        self.assertEqual(rock_selection_id(19, 102), "d:102")
        self.assertNotEqual(rock_selection_id(19, 101), rock_selection_id(19, 102))

    def test_legacy_rock_falls_back_to_physical_sample_id(self) -> None:
        self.assertEqual(rock_selection_id(19, None), "r:19")


if __name__ == "__main__":
    unittest.main()
