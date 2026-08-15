from __future__ import annotations

from petrolab.ui.project_context import _clear_transient_project_state


def main() -> None:
    state = {
        "workflow_plot_analysis_ids": ["a1"],
        "workflow_table_dataset_ids": [7],
        "workflow_edit_context": {"project_id": 1},
        "grain_profile_analysis_ids": ["a2"],
        "quick_import_done_ids": [8],
        "universal_study_id_p1_file": 15,
        "univimg_index_p1_batch": 2,
        "v0151_post_import_image_dataset_1": 8,
        "whole_rock_workspace_context": {"project_id": 1},
        "rock_workspace_edit_id": 4,
        "publication_composer_preset": "Lithos",
        "style_profile_select": "Default",
        "nav_route": "plots",
        "appearance": "dark",
    }
    removed = set(_clear_transient_project_state(state))
    expected = {
        "workflow_plot_analysis_ids",
        "workflow_table_dataset_ids",
        "workflow_edit_context",
        "grain_profile_analysis_ids",
        "quick_import_done_ids",
        "universal_study_id_p1_file",
        "univimg_index_p1_batch",
        "v0151_post_import_image_dataset_1",
        "whole_rock_workspace_context",
        "rock_workspace_edit_id",
    }
    assert expected.issubset(removed)
    assert not expected.intersection(state)
    assert state["publication_composer_preset"] == "Lithos"
    assert state["style_profile_select"] == "Default"
    assert state["nav_route"] == "plots"
    assert state["appearance"] == "dark"

    print("project-switch transient-state tests: OK")


if __name__ == "__main__":
    main()
