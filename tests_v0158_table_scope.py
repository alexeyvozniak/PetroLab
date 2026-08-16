from __future__ import annotations

import pandas as pd


def test_scope_counts_keep_universe_visible_and_selection_distinct() -> None:
    from petrolab.ui.table_scope import table_scope_caption, table_scope_counts

    universe = pd.DataFrame({"_analysis_id": ["a1", "a2", "b1", "b2"]})
    visible = universe.loc[universe["_analysis_id"].isin(["b1", "b2"])].copy()
    counts = table_scope_counts(universe, visible, ["a1", "b1", "outside"])
    assert counts == {
        "universe": 4,
        "visible": 2,
        "selection": 3,
        "selection_here": 2,
        "selection_visible": 1,
        "selection_outside": 1,
    }
    caption = table_scope_caption(counts)
    assert "Всего · 4" in caption
    assert "В виде · 2" in caption
    assert "Selection · 3" in caption
    assert "здесь · 2" in caption
    assert "вне текущего контекста · 1" in caption


def test_filtering_view_does_not_redefine_universe_or_selection() -> None:
    from petrolab.ui.table_scope import table_scope_counts

    universe = pd.DataFrame(
        {
            "_analysis_id": ["a1", "a2", "b1"],
            "Article": ["A", "A", "B"],
        }
    )
    visible = universe.loc[universe["Article"].eq("B")]
    counts = table_scope_counts(universe, visible, ["a1", "b1"])
    assert counts["universe"] == 3
    assert counts["visible"] == 1
    assert counts["selection"] == 2
    assert counts["selection_here"] == 2
    assert counts["selection_visible"] == 1


def test_duplicate_dataframe_index_does_not_inflate_analysis_counts() -> None:
    from petrolab.ui.table_scope import table_scope_counts

    universe = pd.DataFrame({"_analysis_id": ["a1", "a1", "a2"]})
    visible = universe.iloc[:2]
    counts = table_scope_counts(universe, visible, ["a1"])
    assert counts["universe"] == 2
    assert counts["visible"] == 1
    assert counts["selection"] == 1


def main() -> None:
    test_scope_counts_keep_universe_visible_and_selection_distinct()
    test_filtering_view_does_not_redefine_universe_or_selection()
    test_duplicate_dataframe_index_does_not_inflate_analysis_counts()
    print("v0.15.8 Data Workspace scope clarity: OK")


if __name__ == "__main__":
    main()
