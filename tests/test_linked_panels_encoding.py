from __future__ import annotations

import pandas as pd

from petrolab.ui.linked_panels import build_linked_panel_figure


def test_linked_panels_encode_color_and_marker_independently() -> None:
    dataframe = pd.DataFrame(
        {
            "_analysis_id": ["a-1", "a-2", "a-3", "a-4"],
            "Generation": ["Core", "Core", "Rim", "Rim"],
            "Method": ["EPMA", "LA-ICP-MS", "EPMA", "LA-ICP-MS"],
            "TiO2": [1.0, 1.1, 1.2, 1.3],
            "MgO": [18.0, 18.5, 19.0, 19.5],
        }
    )

    figure = build_linked_panel_figure(
        dataframe,
        [{"x": "TiO2", "y": "MgO"}],
        id_column="_analysis_id",
        color_column="Generation",
        marker_column="Method",
    )

    assert len(figure.data) == 4
    assert {trace.name for trace in figure.data} == {"Core", "Rim"}
    assert {trace.marker.symbol for trace in figure.data} == {"circle", "square"}
    assert len({trace.marker.color for trace in figure.data if trace.name == "Core"}) == 1
    assert len({trace.marker.color for trace in figure.data if trace.name == "Rim"}) == 1
