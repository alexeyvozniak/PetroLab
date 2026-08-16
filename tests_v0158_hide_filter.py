from __future__ import annotations

import pandas as pd


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "_analysis_id": ["a1", "a2", "b1", "b2"],
            "Источник / статья": ["Article A", "Article A", "Article B", "Article B"],
            "Минерал": ["apatite", "mica", "apatite", "mica"],
        }
    )


def test_hide_article_changes_view_not_selection() -> None:
    from petrolab.ui.selection_context import read_selection, set_selection
    from petrolab.ui.table_filters import apply_categorical_filter

    frame = _frame()
    state: dict[str, object] = {}
    set_selection(["a1", "b1"], origin="comparison", state=state)
    visible = apply_categorical_filter(
        frame,
        "Источник / статья",
        ["Article A"],
        mode="Скрыть",
    )
    assert visible["_analysis_id"].tolist() == ["b1", "b2"]
    assert read_selection(state).analysis_ids == ("a1", "b1")


def test_include_and_hide_modes_are_exact_opposites_for_chosen_values() -> None:
    from petrolab.ui.table_filters import apply_categorical_filter

    frame = _frame()
    included = apply_categorical_filter(frame, "Минерал", ["apatite"], mode="Оставить")
    hidden = apply_categorical_filter(frame, "Минерал", ["apatite"], mode="Скрыть")
    assert included["_analysis_id"].tolist() == ["a1", "b1"]
    assert hidden["_analysis_id"].tolist() == ["a2", "b2"]
    assert set(included["_analysis_id"]) | set(hidden["_analysis_id"]) == set(frame["_analysis_id"])


def test_saved_view_roundtrip_preserves_hide_mode() -> None:
    from petrolab.ui.table_view_state import TableViewState, apply_table_view, capture_table_view

    prefix = "analysis"
    source: dict[str, object] = {
        f"{prefix}_filter_column": "Источник / статья",
        f"{prefix}_filter_mode_Источник / статья": "Скрыть",
        f"{prefix}_filter_values_Источник / статья": ["Article A"],
    }
    captured = capture_table_view(source, prefix)
    assert captured.filter_mode == "Скрыть"
    assert captured.filter_values == ["Article A"]

    restored: dict[str, object] = {}
    apply_table_view(restored, prefix, TableViewState.from_dict(captured.to_dict()))
    assert restored[f"{prefix}_filter_mode_Источник / статья"] == "Скрыть"
    assert restored[f"{prefix}_filter_values_Источник / статья"] == ["Article A"]


def test_old_saved_view_without_filter_mode_defaults_to_include() -> None:
    from petrolab.ui.table_view_state import TableViewState

    legacy = TableViewState.from_dict(
        {
            "filter_column": "Источник / статья",
            "filter_values": ["Article B"],
        }
    )
    assert legacy.filter_mode == "Оставить"


def main() -> None:
    test_hide_article_changes_view_not_selection()
    test_include_and_hide_modes_are_exact_opposites_for_chosen_values()
    test_saved_view_roundtrip_preserves_hide_mode()
    test_old_saved_view_without_filter_mode_defaults_to_include()
    print("v0.15.8 reversible categorical hide filter: OK")


if __name__ == "__main__":
    main()
