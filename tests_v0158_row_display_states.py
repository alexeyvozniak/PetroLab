from __future__ import annotations


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


def main() -> None:
    test_display_states_are_independent_from_selection_and_science()
    test_display_state_can_be_removed_without_touching_hide_exclude()
    test_partial_color_or_marker_reset_is_independent()
    print("v0.15.8 JMP row display states: OK")


if __name__ == "__main__":
    main()
