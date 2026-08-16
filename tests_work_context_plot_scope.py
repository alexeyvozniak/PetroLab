from petrolab.ui.smart_plot_start import consume_plot_scope, seed_selection_plot_handoff
from petrolab.ui.work_context import WORK_CONTEXT_REVISION_KEY


def main() -> None:
    state = {WORK_CONTEXT_REVISION_KEY: 7}
    seed_selection_plot_handoff(
        state,
        dataset_ids=[10],
        analysis_ids=["search-a", "search-b"],
        origin="Поиск",
    )
    exact = consume_plot_scope(
        state,
        project_id=1,
        available_dataset_ids=[10, 20],
        work_context={"dataset_ids": [10], "analysis_ids": ["old-context"], "label": "Old sample"},
    )
    assert exact.explicit is True
    assert exact.dataset_ids == (10,)
    assert exact.analysis_ids == ("search-a", "search-b")

    # Local graph presentation can evolve freely while that WorkContext revision is unchanged.
    state["quick_log_x"] = True
    state["quick_plot_visibility_filters"] = {"source": ["Search paper"]}
    same = consume_plot_scope(
        state,
        project_id=1,
        available_dataset_ids=[10, 20],
        work_context={"dataset_ids": [10], "analysis_ids": ["old-context"], "label": "Old sample"},
    )
    assert same.analysis_ids == ("search-a", "search-b")
    assert state["quick_log_x"] is True

    # Opening a materially new Sample/dataset/thin-section increments WorkContext revision.
    # On the next Graphs visit the new WorkContext must retire the old search scope.
    state[WORK_CONTEXT_REVISION_KEY] = 8
    new_context = {
        "dataset_ids": [20],
        "analysis_ids": ["sample-b1", "sample-b2"],
        "label": "Sample B",
        "sample": "B",
    }
    resolved = consume_plot_scope(
        state,
        project_id=1,
        available_dataset_ids=[10, 20],
        work_context=new_context,
    )
    assert resolved.explicit is False
    assert resolved.dataset_ids == (20,)
    assert resolved.analysis_ids == ("sample-b1", "sample-b2")
    assert resolved.context_label == "Sample B"
    assert "quick_log_x" not in state
    assert "quick_plot_visibility_filters" not in state

    print("WorkContext revision -> plot scope invalidation: OK")


if __name__ == "__main__":
    main()
