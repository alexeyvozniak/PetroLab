from __future__ import annotations

import pandas as pd

from petrolab.ui.linked_panels import build_linked_panel_figure


def _ids_from_trace(trace) -> set[str]:
    custom = trace.customdata
    if custom is None:
        return set()
    return {str(value[0]) for value in custom}


def test_linked_panels_keep_mineral_and_rock_ids_in_binary_ternary_and_spider() -> None:
    dataframe = pd.DataFrame(
        {
            "_analysis_id": ["mineral-1", "rock-1"],
            "Минерал": ["Apatite", None],
            "Rock": [None, "Granodiorite"],
            "Material": ["Mineral", "Rock"],
            "Generation": ["Core", "Whole-rock"],
            "Method": ["EPMA", "XRF"],
            "TiO2": [0.8, 0.6],
            "MgO": [0.2, 1.3],
            "Na2O": [0.4, 3.6],
            "K2O": [0.1, 2.8],
            "CaO": [54.0, 5.1],
            "La_N": [8.0, 60.0],
            "Ce_N": [7.0, 58.0],
            "Nd_N": [5.0, 45.0],
        }
    )
    panels = [
        {"kind": "xy", "x": "TiO2", "y": "MgO"},
        {"kind": "ternary", "a": "Na2O", "b": "K2O", "c": "CaO"},
        {"kind": "spider", "variables": ["La_N", "Ce_N", "Nd_N"], "log_y": True},
    ]

    figure = build_linked_panel_figure(
        dataframe,
        panels,
        id_column="_analysis_id",
        selected_ids=["rock-1"],
        color_column="Material",
        marker_column="Method",
    )

    kinds = {trace.meta["panel_kind"] for trace in figure.data if trace.meta}
    assert kinds == {"xy", "ternary", "spider"}
    assert any(trace.type == "scatterternary" for trace in figure.data)
    assert any(trace.meta["analysis_id"] == "rock-1" for trace in figure.data if trace.meta["panel_kind"] == "spider")

    all_ids = set().union(*(_ids_from_trace(trace) for trace in figure.data))
    assert {"mineral-1", "rock-1"} <= all_ids

    selected_binary = [
        trace for trace in figure.data
        if trace.meta["panel_kind"] == "xy" and "rock-1" in _ids_from_trace(trace)
    ]
    selected_ternary = [
        trace for trace in figure.data
        if trace.meta["panel_kind"] == "ternary" and "rock-1" in _ids_from_trace(trace)
    ]
    assert selected_binary[0].selectedpoints == (0,)
    assert selected_ternary[0].selectedpoints == (0,)


def test_linked_panels_recognise_mixed_material_scope() -> None:
    dataframe = pd.DataFrame(
        {
            "_analysis_id": ["m1", "r1"],
            "Минерал": ["Olivine", None],
            "Lithology": [None, "Basalt"],
            "SiO2": [40.0, 51.0],
            "MgO": [47.0, 7.0],
        }
    )

    figure = build_linked_panel_figure(
        dataframe,
        [{"x": "SiO2", "y": "MgO"}],
        id_column="_analysis_id",
        selected_ids=["r1"],
    )

    assert figure.data[0].customdata[0][0] == "m1"
    assert figure.data[0].selectedpoints == (1,)
