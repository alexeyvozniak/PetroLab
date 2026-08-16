from __future__ import annotations

import pandas as pd


def test_series_selection_maps_human_series_to_analysis_ids() -> None:
    from petrolab.ui.plot_manager import _selected_series_ids

    dataframe = pd.DataFrame(
        {
            "_analysis_id": ["a1", "a2", "b1", "b2"],
            "Источник": ["Article A", "Article A", "Article B", "Article B"],
            "SiO2": [40.0, 41.0, 42.0, 43.0],
        }
    )
    edited = pd.DataFrame(
        {
            "В отбор": [True, False],
            "Серия": ["Article A", "Article B"],
        }
    )
    ids, names = _selected_series_ids(dataframe, "Источник", edited)
    assert names == ["Article A"]
    assert ids == ["a1", "a2"]


def test_series_selection_is_separate_from_visibility_and_row_state() -> None:
    from petrolab.ui.plot_manager import _selected_series_ids
    from petrolab.ui.selection_context import read_row_states, read_selection, set_selection, set_row_state

    dataframe = pd.DataFrame(
        {
            "_analysis_id": ["a1", "a2", "b1"],
            "Generation": ["core", "core", "rim"],
        }
    )
    edited = pd.DataFrame(
        {
            "Показывать": [False, True],
            "В отбор": [True, False],
            "Серия": ["core", "rim"],
        }
    )
    ids, _ = _selected_series_ids(dataframe, "Generation", edited)
    state: dict[str, object] = {}
    set_row_state("hidden", ["b1"], mode="add", state=state)
    set_selection(ids, origin="Серии · Generation", mode="replace", state=state)

    assert read_selection(state).analysis_ids == ("a1", "a2")
    assert read_row_states(state).hidden == ("b1",)
    assert dataframe["_analysis_id"].tolist() == ["a1", "a2", "b1"]


def main() -> None:
    test_series_selection_maps_human_series_to_analysis_ids()
    test_series_selection_is_separate_from_visibility_and_row_state()
    print("v0.15.8 linked series selection: OK")


if __name__ == "__main__":
    main()
