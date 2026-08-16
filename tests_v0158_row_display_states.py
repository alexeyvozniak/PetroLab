from __future__ import annotations

import pandas as pd


def test_display_states_are_independent_from_selection_and_science() -> None:
    from petrolab.ui.selection_context import (
        read_row_states,
        read_selection,
        set_row_display,
        set_row_state,
        set_selection,
    )

    state: dict[str, object] = {}
    set_selection(["a1", "a2"], origin="test", state=state)
    set_row_state("hidden", ["a3"], mode="add", state=state)
    set_row_state("excluded", ["a4"], mode="add", state=state)
    set_row_state("labelled", ["a1"], mode="add", state=state)
    set_row_display(["a1", "a2"], color="#ff0000", marker="D", state=state)

    selection = read_selection(state)
    rows = read_row_states(state)
    assert selection.analysis_ids == ("a1", "a2")
    assert rows.hidden == ("a3",)
    assert rows.excluded == ("a4",)
    assert rows.labelled == ("a1",)
    assert rows.display_color == {"a1": "#ff0000", "a2": "#ff0000"}
    assert rows.display_marker == {"a1": "D", "a2": "D"}

    set_selection(["b1"], origin="other", mode="replace", state=state)
    rows_after = read_row_states(state)
    assert read_selection(state).analysis_ids == ("b1",)
    assert rows_after.labelled == ("a1",)
    assert rows_after.display_color["a2"] == "#ff0000"


def test_display_state_can_be_removed_without_touching_hide_exclude() -> None:
    from petrolab.ui.selection_context import (
        clear_row_display,
        read_row_states,
        set_row_display,
        set_row_state,
    )

    state: dict[str, object] = {}
    set_row_state("hidden", ["a1"], mode="add", state=state)
    set_row_state("excluded", ["a2"], mode="add", state=state)
    set_row_state("labelled", ["a1", "a2"], mode="add", state=state)
    set_row_display(["a1", "a2"], color="#00aa00", marker="s", state=state)

    clear_row_display(["a1"], state=state)
    rows = read_row_states(state)
    assert rows.hidden == ("a1",)
    assert rows.excluded == ("a2",)
    assert rows.labelled == ("a2",)
    assert "a1" not in rows.display_color and rows.display_color["a2"] == "#00aa00"
    assert "a1" not in rows.display_marker and rows.display_marker["a2"] == "s"

    clear_row_display(state=state)
    rows = read_row_states(state)
    assert rows.hidden == ("a1",)
    assert rows.excluded == ("a2",)
    assert rows.labelled == ()
    assert rows.display_color == {}
    assert rows.display_marker == {}


def test_partial_color_or_marker_reset_is_independent() -> None:
    from petrolab.ui.selection_context import read_row_states, set_row_display

    state: dict[str, object] = {}
    set_row_display(["a1"], color="#112233", marker="^", state=state)
    set_row_display(["a1"], clear_color=True, state=state)
    rows = read_row_states(state)
    assert rows.display_color == {}
    assert rows.display_marker == {"a1": "^"}
    set_row_display(["a1"], clear_marker=True, state=state)
    assert read_row_states(state).display_marker == {}


def _plot_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "_analysis_id": ["a1", "a2", "a3"],
            "Sample": ["KIV-2", "KIV-2", "PG-6"],
            "Grain": ["g1", "g1", "g2"],
            "Point": ["p1", "p2", "p3"],
            "Generation": ["core", "rim", "core"],
            "TiO2": [1.0, 2.0, 3.0],
            "Al2O3": [10.0, 11.0, 12.0],
        }
    )


def test_single_xy_overlay_uses_human_label_color_marker_and_analysis_id() -> None:
    from petrolab.interactive_plotting import build_interactive_scatter

    figure = build_interactive_scatter(
        _plot_frame(),
        "TiO2",
        "Al2O3",
        "Generation",
        labelled_ids=["a1"],
        excluded_ids=[],
        display_color={"a1": "#ff0000"},
        display_marker={"a1": "D"},
    )
    overlays = [trace for trace in figure.data if getattr(trace, "name", "") == "Временная маркировка"]
    assert len(overlays) == 1
    overlay = overlays[0]
    assert overlay.marker.color == "#ff0000"
    assert overlay.marker.symbol == "diamond"
    assert overlay.customdata[0][0] == "a1"
    assert "KIV-2" in str(overlay.text[0])
    assert "a1" not in str(overlay.text[0])


def test_excluded_analysis_stays_in_scatter_and_gets_visible_cross_overlay() -> None:
    from petrolab.interactive_plotting import build_interactive_scatter

    frame = _plot_frame()
    figure = build_interactive_scatter(
        frame,
        "TiO2",
        "Al2O3",
        "Generation",
        labelled_ids=[],
        excluded_ids=["a2"],
        display_color={},
        display_marker={},
    )
    excluded = [trace for trace in figure.data if getattr(trace, "name", "") == "Исключено из статистики"]
    assert len(excluded) == 1
    trace = excluded[0]
    assert trace.marker.symbol == "x"
    assert trace.customdata[0][0] == "a2"
    assert "KIV-2" in str(trace.text[0])

    base_ids = []
    for base in figure.data:
        if getattr(base, "name", "") in {"core", "rim"} and getattr(base, "customdata", None) is not None:
            base_ids.extend(str(row[0]) for row in base.customdata)
    assert "a2" in base_ids, "Exclude must not hide the analysis from the graph"


def test_linked_panels_render_same_row_display_state_on_every_panel() -> None:
    from petrolab.ui.linked_panels import build_linked_panel_figure

    panels = [
        {"x": "TiO2", "y": "Al2O3", "title": "A"},
        {"x": "Al2O3", "y": "TiO2", "title": "B"},
    ]
    figure = build_linked_panel_figure(
        _plot_frame(),
        panels,
        id_column="_analysis_id",
        group_column="Generation",
        labelled_ids=["a2"],
        excluded_ids=["a3"],
        display_color={"a2": "#00aa00"},
        display_marker={"a2": "s"},
    )
    overlays = [trace for trace in figure.data if getattr(trace, "name", "") == "Временная маркировка"]
    excluded = [trace for trace in figure.data if getattr(trace, "name", "") == "Исключено из статистики"]
    assert len(overlays) == 2
    assert len(excluded) == 2
    assert all(trace.customdata[0][0] == "a2" for trace in overlays)
    assert all(trace.marker.color == "#00aa00" for trace in overlays)
    assert all(trace.marker.symbol == "square" for trace in overlays)
    assert all("KIV-2" in str(trace.text[0]) for trace in overlays)
    assert all(trace.customdata[0][0] == "a3" for trace in excluded)
    assert all(trace.marker.symbol == "x" for trace in excluded)


def main() -> None:
    test_display_states_are_independent_from_selection_and_science()
    test_display_state_can_be_removed_without_touching_hide_exclude()
    test_partial_color_or_marker_reset_is_independent()
    test_single_xy_overlay_uses_human_label_color_marker_and_analysis_id()
    test_excluded_analysis_stays_in_scatter_and_gets_visible_cross_overlay()
    test_linked_panels_render_same_row_display_state_on_every_panel()
    print("v0.15.8 JMP row display states: OK")


if __name__ == "__main__":
    main()
