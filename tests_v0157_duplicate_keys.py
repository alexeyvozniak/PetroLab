"""Regression: reusable chemical-selection wrapper must not use a fixed widget key.

Audit v0.15.7 #1: ``StreamlitDuplicateElementKey: key='v0154_clear_chemical_selection'``
happens because ``_advanced_interactive_with_memory`` rendered its "Сбросить отбор"
button with a hard-coded key even though the wrapper can appear more than once in one
Streamlit tree.  The fix scopes every element key by a per-plot ``key_prefix``.

These tests drive a real Streamlit AppTest tree (not source text), so a regression to
a fixed or colliding key will raise ``StreamlitDuplicateElementKeyError`` and fail.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from petrolab.ui.workflow_continuity_v0154 import _interactive_key_prefix


_APP_SCRIPT = """
from types import SimpleNamespace

import streamlit as st

from petrolab.ui.workflow_continuity_v0154 import (
    _IGNORE_SELECTION_ONCE,
    _PERSISTENT_CHEMICAL_SELECTION,
    _advanced_interactive_with_memory,
)

# Simulate the reported scenario: a persistent chemical selection exists and the
# reusable wrapper renders more than once in one tree (two plot instances).
st.session_state[_PERSISTENT_CHEMICAL_SELECTION] = ["analysis-a", "analysis-b"]
st.session_state.pop(_IGNORE_SELECTION_ONCE, None)


def dummy_original(*args, **kwargs):
    st.caption("dummy plot body")


xy = SimpleNamespace(
    selected_analysis_ids=lambda event: [],
    build_interactive_scatter=lambda *a, **k: None,
)

_advanced_interactive_with_memory(
    dummy_original,
    xy,
    "chem_prefix_one",
    "dataframe", 7, "SiO2", "MgO", None,
)
_advanced_interactive_with_memory(
    dummy_original,
    xy,
    "chem_prefix_two",
    "dataframe", 7, "Al", "MgO", None,
)

st.caption("two instances rendered without a duplicate element key")
"""

_BAD_SCRIPT = _APP_SCRIPT.replace(
    '"chem_prefix_two"',
    '"chem_prefix_one"',
)


def _run_app(script_source: str) -> AppTest:
    with tempfile.TemporaryDirectory(prefix="petrolab_dupkey_") as tmp:
        script = Path(tmp) / "dupkey_app.py"
        script.write_text(script_source, encoding="utf-8")
        return AppTest.from_file(str(script), default_timeout=30).run(timeout=30)


class DuplicateKeyRegressionTests(unittest.TestCase):
    def test_two_wrapper_instances_render_without_duplicate_key(self) -> None:
        app = _run_app(_APP_SCRIPT)
        assert not app.exception, [str(item.value) for item in app.exception]
        labels = [str(button.label) for button in app.button]
        self.assertEqual(labels.count("Сбросить отбор"), 2)

    def test_reused_prefix_is_caught_as_duplicate_key(self) -> None:
        """Guard: the harness itself detects the original failure mode."""
        app = _run_app(_BAD_SCRIPT)
        self.assertTrue(app.exception, "Expected DuplicateElementKey for a reused key")
        details = "\n".join(str(item.value) for item in app.exception)
        self.assertIn("multiple elements with the same `key=", details)

    def test_key_prefix_is_stable_per_plot_instance(self) -> None:
        frame = pd.DataFrame({"_analysis_id": ["a"], "_dataset_id": [41]})
        first = _interactive_key_prefix(frame, 7, "SiO2", "MgO", None)
        second = _interactive_key_prefix(frame, 7, "SiO2", "MgO", None)
        other = _interactive_key_prefix(frame, 7, "Al", "MgO", None)
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertTrue(first.startswith("v0154_chem_"))


if __name__ == "__main__":
    unittest.main()