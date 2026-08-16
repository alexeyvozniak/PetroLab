from __future__ import annotations

import unittest

from petrolab.ui.selection_context import (
    clear_row_states,
    clear_selection,
    read_row_states,
    read_selection,
    set_row_state,
    set_selection,
)


class SelectionContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.state: dict = {}

    def test_replace_add_subtract_preserve_order_and_deduplicate(self) -> None:
        first = set_selection(["a", "b", "a"], origin="table", state=self.state)
        self.assertEqual(first.analysis_ids, ("a", "b"))
        added = set_selection(["b", "c"], origin="xy", mode="add", state=self.state)
        self.assertEqual(added.analysis_ids, ("a", "b", "c"))
        remaining = set_selection(["b", "missing"], origin="xy", mode="subtract", state=self.state)
        self.assertEqual(remaining.analysis_ids, ("a", "c"))

    def test_metadata_and_origin_are_shared_with_the_selection(self) -> None:
        selection = set_selection(
            ["x1", "x2"], origin="pca", label="Cluster 2", metadata={"cluster": 2}, state=self.state
        )
        self.assertEqual(selection.origin, "pca")
        self.assertEqual(selection.label, "Cluster 2")
        self.assertEqual(selection.metadata["cluster"], 2)
        self.assertEqual(read_selection(self.state).analysis_ids, ("x1", "x2"))

    def test_hidden_and_excluded_are_independent_from_selection(self) -> None:
        set_selection(["a", "b"], origin="table", state=self.state)
        set_row_state("hidden", ["a"], mode="add", state=self.state)
        set_row_state("excluded", ["b"], mode="add", state=self.state)
        states = read_row_states(self.state)
        self.assertEqual(states.hidden, ("a",))
        self.assertEqual(states.excluded, ("b",))
        self.assertEqual(read_selection(self.state).analysis_ids, ("a", "b"))

    def test_clear_operations_do_not_cross_contaminate(self) -> None:
        set_selection(["a"], origin="table", state=self.state)
        set_row_state("hidden", ["a"], state=self.state)
        clear_selection(self.state)
        self.assertFalse(read_selection(self.state).analysis_ids)
        self.assertEqual(read_row_states(self.state).hidden, ("a",))
        clear_row_states(self.state)
        self.assertFalse(read_row_states(self.state).hidden)


if __name__ == "__main__":
    unittest.main()
