from __future__ import annotations

import pandas as pd


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "_analysis_id": ["a1", "a2", "b1", "b2", "u1"],
            "Generation": ["core", "core", "rim", "rim", None],
            "SiO2": [40.0, 41.0, 42.0, 43.0, 44.0],
        }
    )


def test_collapsing_group_only_changes_visible_grid_rows() -> None:
    from petrolab.ui.table_grouping import apply_collapsed_groups

    frame = _frame()
    visible, summary = apply_collapsed_groups(frame, "Generation", ["core"])
    assert visible["_analysis_id"].tolist() == ["b1", "b2", "u1"]
    assert summary == [("core", 2)]
    assert frame["_analysis_id"].tolist() == ["a1", "a2", "b1", "b2", "u1"]


def test_multiple_collapsed_groups_have_readable_counts_and_empty_values() -> None:
    from petrolab.ui.table_grouping import EMPTY_GROUP_LABEL, apply_collapsed_groups, collapsed_summary_text

    visible, summary = apply_collapsed_groups(_frame(), "Generation", ["rim", EMPTY_GROUP_LABEL])
    assert visible["_analysis_id"].tolist() == ["a1", "a2"]
    assert summary == [("rim", 2), (EMPTY_GROUP_LABEL, 1)]
    text = collapsed_summary_text(summary)
    assert "rim · 2" in text
    assert f"{EMPTY_GROUP_LABEL} · 1" in text


def test_collapsed_group_state_roundtrips_in_named_view() -> None:
    from petrolab.ui.table_view_state import TableViewState, apply_table_view, capture_table_view

    prefix = "analysis"
    source: dict[str, object] = {
        f"{prefix}_group_col": "Generation",
        f"{prefix}_collapsed_groups_Generation": ["rim", "core"],
        f"{prefix}_sort_column": "SiO2",
    }
    captured = capture_table_view(source, prefix)
    assert captured.group_column == "Generation"
    assert captured.collapsed_groups == ["rim", "core"]

    restored: dict[str, object] = {}
    apply_table_view(restored, prefix, TableViewState.from_dict(captured.to_dict()))
    assert restored[f"{prefix}_group_col"] == "Generation"
    assert restored[f"{prefix}_collapsed_groups_Generation"] == ["rim", "core"]


def test_legacy_saved_view_without_collapsed_groups_stays_fully_expanded() -> None:
    from petrolab.ui.table_view_state import TableViewState

    legacy = TableViewState.from_dict({"group_column": "Generation"})
    assert legacy.collapsed_groups == []


def test_collapse_does_not_mutate_canonical_selection() -> None:
    from petrolab.ui.selection_context import read_selection, set_selection
    from petrolab.ui.table_grouping import apply_collapsed_groups

    state: dict[str, object] = {}
    set_selection(["a1", "b1"], origin="comparison", state=state)
    visible, _ = apply_collapsed_groups(_frame(), "Generation", ["core"])
    assert "a1" not in visible["_analysis_id"].tolist()
    assert read_selection(state).analysis_ids == ("a1", "b1")


def main() -> None:
    test_collapsing_group_only_changes_visible_grid_rows()
    test_multiple_collapsed_groups_have_readable_counts_and_empty_values()
    test_collapsed_group_state_roundtrips_in_named_view()
    test_legacy_saved_view_without_collapsed_groups_stays_fully_expanded()
    test_collapse_does_not_mutate_canonical_selection()
    print("v0.15.8 collapsible table groups: OK")


if __name__ == "__main__":
    main()
