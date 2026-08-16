from __future__ import annotations

import pandas as pd

from petrolab.interactive_plotting import selected_analysis_ids
from petrolab.ui.linked_panels import build_linked_panel_figure, selection_ids_from_event
from petrolab.ui.plot_spec import PlotSpec, peek_multi_panel_inbox, send_to_multi_panel
from petrolab.ui.selection_context import read_row_states, read_selection, set_row_state, set_selection


def _plotly_event(*analysis_ids: str) -> dict:
    return {
        "selection": {
            "points": [
                {
                    "curve_number": 0,
                    "point_number": index,
                    "customdata": [analysis_id, "PG-1", "G1", f"P{index + 1}"],
                }
                for index, analysis_id in enumerate(analysis_ids)
            ]
        }
    }


def main() -> None:
    # The ordinary XY and multi-panel event adapters must interpret the same
    # immutable analysis_id payload and deduplicate repeated Plotly points.
    event = _plotly_event("a2", "a3", "a2")
    assert selected_analysis_ids(event) == ["a2", "a3"]
    assert selection_ids_from_event(event) == ["a2", "a3"]

    # JMP-like selection is one shared transient row state, independent of the
    # page that produced it. Replace/Add/Subtract operate on the same IDs.
    state: dict = {}
    selected = set_selection(
        selected_analysis_ids(event), origin="XY", mode="replace", state=state
    )
    assert selected.analysis_ids == ("a2", "a3")

    selected = set_selection(["a4"], origin="Table", mode="add", state=state)
    assert selected.analysis_ids == ("a2", "a3", "a4")

    selected = set_selection(["a3"], origin="PCA", mode="subtract", state=state)
    assert selected.analysis_ids == ("a2", "a4")
    assert read_selection(state).analysis_ids == ("a2", "a4")

    # Hide/Exclude are independent row states and must not mutate Selection.
    set_row_state("hidden", ["a1"], state=state)
    set_row_state("excluded", ["a5"], state=state)
    row_states = read_row_states(state)
    assert row_states.hidden == ("a1",)
    assert row_states.excluded == ("a5",)
    assert read_selection(state).analysis_ids == ("a2", "a4")

    # A configured XY graph carries the exact same analysis IDs into the
    # multi-panel inbox; axes/grouping/style are transferred with it.
    spec = PlotSpec(
        dataset_ids=(10, 11),
        analysis_ids=read_selection(state).analysis_ids,
        x="Al2O3",
        y="TiO2",
        group_column="Generation",
        title="Mica evolution",
        visible_sources=("Study A",),
        hidden_sources=("Study B",),
        style_map={"core": {"marker": "circle"}},
    )
    send_to_multi_panel(spec, state=state)
    restored = peek_multi_panel_inbox(state=state)
    assert restored is not None
    assert restored.analysis_ids == ("a2", "a4")
    assert (restored.x, restored.y, restored.group_column) == (
        "Al2O3", "TiO2", "Generation"
    )
    assert restored.visible_sources == ("Study A",)
    assert restored.hidden_sources == ("Study B",)

    # The linked multi-panel renderer highlights those exact IDs, proving that
    # the same SelectionContext can be visualized without page-local selection.
    frame = pd.DataFrame(
        {
            "_analysis_id": ["a1", "a2", "a3", "a4", "a5"],
            "Al2O3": [10.0, 11.0, 12.0, 13.0, 14.0],
            "TiO2": [1.0, 1.5, 2.0, 2.5, 3.0],
            "Generation": ["core", "core", "rim", "rim", "rim"],
        }
    )
    figure = build_linked_panel_figure(
        frame,
        [{"x": "Al2O3", "y": "TiO2"}],
        id_column="_analysis_id",
        selected_ids=restored.analysis_ids,
        group_column="Generation",
    )
    highlighted: set[str] = set()
    for trace in figure.data:
        for index in list(trace.selectedpoints or []):
            highlighted.add(str(trace.customdata[index][0]))
    assert highlighted == {"a2", "a4"}, highlighted

    print("v0.15.7 linked-selection integration gate: OK")


if __name__ == "__main__":
    main()
