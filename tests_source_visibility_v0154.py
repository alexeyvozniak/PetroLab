from __future__ import annotations

import unittest

import pandas as pd

from petrolab.source_registry import SOURCE_LABEL_COLUMN
from petrolab.ui.source_controls import (
    apply_plot_visibility_filters,
    available_visibility_dimensions,
)


def _dimension(frame: pd.DataFrame, key: str):
    return next(item for item in available_visibility_dimensions(frame) if item.key == key)


class SourceVisibilityV0154Tests(unittest.TestCase):
    def test_row_source_has_priority_over_dataset_source(self):
        frame = pd.DataFrame({
            "Source": ["Smith 2014", "Jones 2018", "Smith 2014"],
            SOURCE_LABEL_COLUMN: ["Compilation 2020"] * 3,
            "Sample": ["A", "B", "C"],
        })
        source = _dimension(frame, "source")
        self.assertEqual(source.column, "Source")
        visible, hidden = apply_plot_visibility_filters(frame, {"source": ["Smith 2014"]})
        self.assertEqual(visible["Sample"].tolist(), ["A", "C"])
        self.assertEqual(hidden["Sample"].tolist(), ["B"])

    def test_canonical_sample_has_priority_when_present(self):
        frame = pd.DataFrame({
            "Canonical Sample": ["Kandalaksha", "Kandalaksha"],
            "Sample": ["Кандалакша", "kandalaksha"],
            "Source": ["A", "B"],
        })
        sample = _dimension(frame, "sample")
        self.assertEqual(sample.column, "Canonical Sample")
        visible, hidden = apply_plot_visibility_filters(frame, {"sample": ["Kandalaksha"]})
        self.assertEqual(len(visible), 2)
        self.assertTrue(hidden.empty)

    def test_dataset_source_remains_backward_compatible(self):
        frame = pd.DataFrame({
            SOURCE_LABEL_COLUMN: ["Reguir et al., 2009", "Other 2010"],
            "Sample": ["A", "B"],
        })
        source = _dimension(frame, "source")
        self.assertEqual(source.column, SOURCE_LABEL_COLUMN)
        visible, _ = apply_plot_visibility_filters(frame, {"source": ["Reguir et al., 2009"]})
        self.assertEqual(visible["Sample"].tolist(), ["A"])


if __name__ == "__main__":
    unittest.main()
