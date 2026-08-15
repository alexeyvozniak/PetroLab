from __future__ import annotations

import pandas as pd

from petrolab.ui.pages.v0151_wrappers import _tokenized_literal_search, _update_exact_selection_state


def test_multi_token_search_matches_across_different_columns():
    frame = pd.DataFrame([
        {"Mineral": "apatite", "Источник / статья": "Reguir et al., 2009", "Sample": "A"},
        {"Mineral": "apatite", "Источник / статья": "Other et al., 2020", "Sample": "B"},
    ])
    # The production search module only searches known source-label columns; use its exact label if present.
    import petrolab.ui.pages.global_search as search
    source_column = next((column for column in frame.columns if column in search._SEARCH_COLUMNS), None)
    if source_column is None:
        # SOURCE_LABEL_COLUMN is imported into _SEARCH_COLUMNS; reconstruct a matching frame.
        from petrolab.source_registry import SOURCE_LABEL_COLUMN
        frame = frame.rename(columns={"Источник / статья": SOURCE_LABEL_COLUMN})
    result = _tokenized_literal_search(frame, "apatite Reguir")
    assert len(result) == 1
    assert result.iloc[0]["Mineral"] == "apatite"


def test_exact_selection_survives_reruns_and_dataset_only_route_clears_it():
    state = {
        "workflow_plot_dataset_ids": [1],
        "workflow_plot_analysis_ids": ["a1", "a2"],
    }
    exact = _update_exact_selection_state(state, "persist")
    assert exact == ["a1", "a2"]
    state.pop("workflow_plot_dataset_ids", None)
    state.pop("workflow_plot_analysis_ids", None)
    exact = _update_exact_selection_state(state, "persist")
    assert exact == ["a1", "a2"]
    assert state["workflow_plot_analysis_ids"] == ["a1", "a2"]

    state = {"persist": ["a1"], "workflow_plot_dataset_ids": [2]}
    exact = _update_exact_selection_state(state, "persist")
    assert exact == []
    assert "persist" not in state


if __name__ == "__main__":
    test_multi_token_search_matches_across_different_columns()
    test_exact_selection_survives_reruns_and_dataset_only_route_clears_it()
    print("v0.15.1 UI selection tests: OK")
