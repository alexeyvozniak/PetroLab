from __future__ import annotations

import unittest

from petrolab.ui.navigation_state import MAX_HISTORY, can_go_back, go_back, push_current


class NavigationStateTests(unittest.TestCase):
    def test_back_restores_route_and_work_context(self) -> None:
        state = {
            "nav_route": "workspace",
            "_petrolab_work_context": {"project_id": 1, "label": "Sample A", "analysis_ids": ["a"]},
            "workflow_plot_dataset_ids": [10],
        }
        push_current(state, current_route="workspace")
        state["nav_route"] = "plots"
        state["_petrolab_work_context"] = {"project_id": 1, "label": "Sample B", "analysis_ids": ["b"]}
        state["workflow_plot_dataset_ids"] = [11]

        route = go_back(state, current_route="plots", valid_routes={"workspace", "plots"})

        self.assertEqual(route, "workspace")
        self.assertEqual(state["nav_route"], "workspace")
        self.assertEqual(state["_petrolab_work_context"]["label"], "Sample A")
        self.assertEqual(state["workflow_plot_dataset_ids"], [10])

    def test_history_is_bounded_and_deduplicates_same_snapshot(self) -> None:
        state = {"nav_route": "home"}
        push_current(state, current_route="home")
        push_current(state, current_route="home")
        self.assertEqual(len(state["_petrolab_nav_history"]), 1)
        for index in range(MAX_HISTORY + 7):
            state["workflow_plot_dataset_ids"] = [index]
            push_current(state, current_route="plots")
        self.assertEqual(len(state["_petrolab_nav_history"]), MAX_HISTORY)
        self.assertTrue(can_go_back(state))

    def test_back_skips_invalid_and_current_routes(self) -> None:
        state = {
            "nav_route": "plots",
            "_petrolab_nav_history": [
                {"route": "home", "state": {}},
                {"route": "removed_route", "state": {}},
                {"route": "plots", "state": {}},
            ],
        }
        route = go_back(state, current_route="plots", valid_routes={"home", "plots"})
        self.assertEqual(route, "home")


if __name__ == "__main__":
    unittest.main()
