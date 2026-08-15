from __future__ import annotations

import unittest

import pandas as pd
import plotly.graph_objects as go

import petrolab  # noqa: F401
from petrolab.import_staging import ROLE_ALIASES, detect_role_columns
from petrolab.term_registry import DEFAULT_TERM_DOMAINS
from petrolab.textural_runtime import (
    SOURCE_TEXTURAL_ZONE_COLUMN,
    TEXTURAL_ZONE_COLUMN,
)
from petrolab.ui.workflow_continuity_v0154 import (
    apply_persistent_selection_to_figure,
    overlay_textural_zone,
)


class TexturalSemanticsTests(unittest.TestCase):
    def test_textural_zone_is_a_separate_canonical_role(self) -> None:
        self.assertIn(TEXTURAL_ZONE_COLUMN, ROLE_ALIASES)
        self.assertIn(TEXTURAL_ZONE_COLUMN, DEFAULT_TERM_DOMAINS)
        self.assertLess(
            list(DEFAULT_TERM_DOMAINS).index(TEXTURAL_ZONE_COLUMN),
            list(DEFAULT_TERM_DOMAINS).index("Generation"),
        )

    def test_russian_textural_headers_are_detected_without_using_generic_location(self) -> None:
        detected = detect_role_columns(["Образец", "Положение в зерне", "SiO2"])
        self.assertEqual(detected.get("Sample"), "Образец")
        self.assertEqual(detected.get(TEXTURAL_ZONE_COLUMN), "Положение в зерне")
        self.assertNotEqual(detected.get("Locality"), "Положение в зерне")

    def test_manual_image_markup_overlays_but_preserves_source_texture(self) -> None:
        frame = pd.DataFrame({
            "_analysis_id": ["a", "b"],
            TEXTURAL_ZONE_COLUMN: ["исходное ядро", "исходная кайма"],
        })
        result = overlay_textural_zone(frame, {"a": {"zone": "белая кайма"}})
        self.assertEqual(result.loc[0, TEXTURAL_ZONE_COLUMN], "белая кайма")
        self.assertEqual(result.loc[1, TEXTURAL_ZONE_COLUMN], "исходная кайма")
        self.assertEqual(result.loc[0, SOURCE_TEXTURAL_ZONE_COLUMN], "исходное ядро")
        self.assertEqual(result.loc[1, SOURCE_TEXTURAL_ZONE_COLUMN], "исходная кайма")

    def test_manual_texture_can_exist_without_source_column(self) -> None:
        frame = pd.DataFrame({"_analysis_id": ["a", "b"]})
        result = overlay_textural_zone(
            frame,
            {"a": {"zone": "ядро"}, "b": {"textural_role": "реакционная зона"}},
        )
        self.assertEqual(result[TEXTURAL_ZONE_COLUMN].tolist(), ["ядро", "реакционная зона"])
        self.assertNotIn(SOURCE_TEXTURAL_ZONE_COLUMN, result.columns)


class PersistentChemicalSelectionTests(unittest.TestCase):
    def test_selected_analysis_ids_are_reapplied_to_plotly_trace(self) -> None:
        figure = go.Figure()
        figure.add_trace(go.Scattergl(
            x=[1.0, 2.0, 3.0],
            y=[10.0, 20.0, 30.0],
            mode="markers",
            customdata=[["a"], ["b"], ["c"]],
        ))
        apply_persistent_selection_to_figure(figure, ["b", "c"])
        self.assertEqual(list(figure.data[0].selectedpoints), [1, 2])

    def test_invisible_selection_does_not_dim_an_unrelated_plot(self) -> None:
        figure = go.Figure()
        figure.add_trace(go.Scattergl(
            x=[1.0, 2.0],
            y=[10.0, 20.0],
            mode="markers",
            customdata=[["a"], ["b"]],
        ))
        apply_persistent_selection_to_figure(figure, ["outside"])
        self.assertIsNone(figure.data[0].selectedpoints)


if __name__ == "__main__":
    unittest.main()
