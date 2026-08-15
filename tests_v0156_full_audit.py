from __future__ import annotations

import unittest
from pathlib import Path

from petrolab.ui.pages.v0156_audit_wrappers import _persist_exact_route
from petrolab.ui.project_context import _clear_transient_project_state


ROOT = Path(__file__).resolve().parent


class ExactRoutePersistenceTests(unittest.TestCase):
    def test_exact_analysis_route_survives_rerun(self) -> None:
        state = {
            "workflow_edit_analysis_ids": ["a-1", "a-2", "a-1"],
            "workflow_edit_dataset_ids": [17],
            "workflow_edit_context": {"scope": "search"},
        }
        exact, datasets, context = _persist_exact_route(
            state,
            incoming_analysis_key="workflow_edit_analysis_ids",
            incoming_dataset_key="workflow_edit_dataset_ids",
            incoming_context_key="workflow_edit_context",
            persistent_analysis_key="_exact_a",
            persistent_dataset_key="_exact_d",
            persistent_context_key="_exact_c",
        )
        self.assertEqual(exact, ["a-1", "a-2"])
        self.assertEqual(datasets, [17])
        self.assertEqual(context, {"scope": "search"})

        state.pop("workflow_edit_analysis_ids", None)
        state.pop("workflow_edit_dataset_ids", None)
        state.pop("workflow_edit_context", None)

        exact2, datasets2, context2 = _persist_exact_route(
            state,
            incoming_analysis_key="workflow_edit_analysis_ids",
            incoming_dataset_key="workflow_edit_dataset_ids",
            incoming_context_key="workflow_edit_context",
            persistent_analysis_key="_exact_a",
            persistent_dataset_key="_exact_d",
            persistent_context_key="_exact_c",
        )
        self.assertEqual(exact2, ["a-1", "a-2"])
        self.assertEqual(datasets2, [17])
        self.assertEqual(context2, {"scope": "search"})
        self.assertEqual(state["workflow_edit_analysis_ids"], ["a-1", "a-2"])
        self.assertEqual(state["workflow_edit_dataset_ids"], [17])

    def test_new_dataset_only_route_clears_old_exact_selection(self) -> None:
        state = {
            "_exact_a": ["old-a"],
            "_exact_d": [1],
            "_exact_c": {"scope": "old"},
            "workflow_edit_dataset_ids": [22],
        }
        exact, datasets, context = _persist_exact_route(
            state,
            incoming_analysis_key="workflow_edit_analysis_ids",
            incoming_dataset_key="workflow_edit_dataset_ids",
            incoming_context_key="workflow_edit_context",
            persistent_analysis_key="_exact_a",
            persistent_dataset_key="_exact_d",
            persistent_context_key="_exact_c",
        )
        self.assertEqual(exact, [])
        self.assertEqual(datasets, [])
        self.assertEqual(context, {})
        self.assertNotIn("workflow_edit_analysis_ids", state)


class ProjectIsolationTests(unittest.TestCase):
    def test_project_switch_clears_identities_not_presentation_preferences(self) -> None:
        state = {
            "workflow_plot_analysis_ids": ["old"],
            "workflow_focus_dataset_id": 19,
            "pending_study_id": 8,
            "thin_section_selected": 101,
            "thin_polygon_55": [(0.1, 0.2)],
            "mixed_dataset": 19,
            "thermodynamics_pressure": 4.0,
            "equilibrium_points": ["old-analysis"],
            "ratio_left": "old-dataset",
            "ternary_interactive_excluded_ids": ["old-analysis"],
            "loaded_ternary_recipe": {"dataset_ids": [19]},
            "partition_rock_context": "lamprophyre",
            "exchange_package_bytes": b"old-package",
            "compare_dataset_ids": [19],
            "history_interpretation_undo": 7,
            "raw_history_undo_id": 99,
            "session_morph_points_3": ["old-point"],
            "_v0151_plot_exact_analysis_ids": ["old"],
            "_pending_destructive_audit_slide_image_3": 3,
            "db_selection_Sample": ["OLD"],
            "multi_panel_label_mode_v0152": "Latin",
            "theme_preference": "dark",
        }
        removed = set(_clear_transient_project_state(state))
        for key in (
            "workflow_plot_analysis_ids",
            "workflow_focus_dataset_id",
            "pending_study_id",
            "thin_section_selected",
            "thin_polygon_55",
            "mixed_dataset",
            "thermodynamics_pressure",
            "equilibrium_points",
            "ratio_left",
            "ternary_interactive_excluded_ids",
            "loaded_ternary_recipe",
            "partition_rock_context",
            "exchange_package_bytes",
            "compare_dataset_ids",
            "history_interpretation_undo",
            "raw_history_undo_id",
            "session_morph_points_3",
            "_v0151_plot_exact_analysis_ids",
            "_pending_destructive_audit_slide_image_3",
            "db_selection_Sample",
        ):
            self.assertIn(key, removed)
            self.assertNotIn(key, state)
        self.assertEqual(state["multi_panel_label_mode_v0152"], "Latin")
        self.assertEqual(state["theme_preference"], "dark")


class SourceContractTests(unittest.TestCase):
    def test_projects_page_uses_central_project_guard(self) -> None:
        source = (ROOT / "petrolab/ui/pages/projects.py").read_text(encoding="utf-8")
        self.assertIn("set_active_project(int(result.project_id))", source)
        self.assertIn("set_active_project(int(project_id))", source)
        self.assertIn("set_active_project(project_id)", source)
        self.assertNotIn('st.session_state["active_project_id"] =', source)
        self.assertNotIn('st.session_state["sidebar_project"] =', source)

    def test_audit_wrappers_cover_all_routed_identity_hotspots(self) -> None:
        source = (ROOT / "petrolab/ui/pages/v0156_audit_wrappers.py").read_text(encoding="utf-8")
        for token in (
            "workflow_edit_analysis_ids",
            "workflow_table_analysis_ids",
            "batch_analysis_ids",
            "workflow_focus_dataset_id",
            "workflow_mixed_dataset_id",
            "workflow_image_dataset_id",
            "workspace_sample_id_pending",
            "workspace_dataset_id_pending",
            "thin_section_focus_id_pending",
            "thin_image_focus_id_pending",
            "multi_panel_thin_section_id",
        ):
            self.assertIn(token, source)

    def test_irreversible_ui_deletes_are_guarded(self) -> None:
        source = (ROOT / "petrolab/ui/pages/v0156_audit_wrappers.py").read_text(encoding="utf-8")
        for prefix in (
            "audit_thin_marker_",
            "audit_thin_field_",
            "audit_slide_marker_",
            "audit_slide_image_",
            "audit_formula_field_",
        ):
            self.assertIn(prefix, source)
        self.assertIn("confirm_then", source)
        self.assertIn("render_pending", source)

    def test_audit_wrappers_are_last_in_page_stack(self) -> None:
        source = (ROOT / "petrolab/ui/pages/__init__.py").read_text(encoding="utf-8")
        audit_pos = source.rfind("from .v0156_audit_wrappers import")
        rock_pos = source.rfind("from .v0154_rock_workspace_wrappers import")
        self.assertGreater(audit_pos, rock_pos)
        for renderer in (
            "render_analyses_page",
            "render_article_tables_page",
            "render_global_search_page",
            "render_images_page",
            "render_multi_panel_page",
            "render_thin_section_workspace_page",
        ):
            self.assertIn(renderer, source[audit_pos:])


if __name__ == "__main__":
    unittest.main()
