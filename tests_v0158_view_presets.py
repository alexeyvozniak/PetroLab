from __future__ import annotations

import pandas as pd


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "_analysis_id": ["a1", "a2", "a3", "a4"],
            "Method": ["EPMA", "LA-ICP-MS", "LA-ICP-MS", "EPMA"],
            "QC решение": ["OK", "warning", "rejected", "OK"],
            "Минерал": ["phlogopite", "apatite", "biotite", "clinopyroxene"],
            "SiO2": [40.0, 41.0, 42.0, 43.0],
            "Nb ppm": [10.0, 20.0, 30.0, 40.0],
        }
    )


def test_data_aware_presets_are_only_created_when_supported() -> None:
    from petrolab.ui.view_presets import builtin_table_view_presets

    presets = {preset.name: preset for preset in builtin_table_view_presets(_frame())}
    assert set(presets) == {"Все анализы", "LA-ICP-MS", "Poor QC", "Слюды"}
    assert presets["LA-ICP-MS"].state.column_mode == "Trace"
    assert presets["LA-ICP-MS"].state.filter_column == "Method"
    assert presets["LA-ICP-MS"].state.filter_values == ["LA-ICP-MS"]
    assert presets["Poor QC"].state.column_mode == "QC"
    assert presets["Poor QC"].state.filter_values == ["rejected", "warning"]
    assert presets["Слюды"].state.column_mode == "Микрозонд"
    assert presets["Слюды"].state.filter_values == ["biotite", "phlogopite"]


def test_presets_never_contain_selection_or_internal_ids() -> None:
    from petrolab.ui.view_presets import builtin_table_view_presets

    for preset in builtin_table_view_presets(_frame()):
        payload = preset.state.to_dict()
        text = " ".join(str(value) for value in payload.values())
        assert "a1" not in text and "a2" not in text
        assert "analysis_id" not in text
        assert "selection" not in text.casefold()
        assert "hidden" not in text.casefold()
        assert "excluded" not in text.casefold()


def test_applying_quick_view_does_not_touch_jmp_row_state() -> None:
    from petrolab.ui.table_view_state import apply_table_view
    from petrolab.ui.view_presets import builtin_table_view_presets

    preset = {item.name: item for item in builtin_table_view_presets(_frame())}["LA-ICP-MS"]
    state: dict[str, object] = {
        "_petrolab_selection_context": {"analysis_ids": ["a1"], "origin": "test"},
        "_petrolab_row_states": {"hidden": ["a2"], "excluded": ["a3"]},
    }
    apply_table_view(state, "analysis", preset.state)
    assert state["analysis_filter_column"] == "Method"
    assert state["analysis_filter_values_Method"] == ["LA-ICP-MS"]
    assert state["_petrolab_selection_context"] == {"analysis_ids": ["a1"], "origin": "test"}
    assert state["_petrolab_row_states"] == {"hidden": ["a2"], "excluded": ["a3"]}


def test_minimal_dataframe_only_offers_all_analyses() -> None:
    from petrolab.ui.view_presets import builtin_table_view_presets

    frame = pd.DataFrame({"Sample": ["A"], "SiO2": [40.0]})
    presets = builtin_table_view_presets(frame)
    assert [preset.name for preset in presets] == ["Все анализы"]


def main() -> None:
    test_data_aware_presets_are_only_created_when_supported()
    test_presets_never_contain_selection_or_internal_ids()
    test_applying_quick_view_does_not_touch_jmp_row_state()
    test_minimal_dataframe_only_offers_all_analyses()
    print("v0.15.8 quick table view presets: OK")


if __name__ == "__main__":
    main()
