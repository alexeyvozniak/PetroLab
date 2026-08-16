from __future__ import annotations

import math

import pandas as pd


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "_analysis_id": ["a1", "a2", "a3", "a4"],
            "TiO2": [1.0, 2.0, 8.0, 9.0],
            "Al2O3": [10.0, 11.0, 18.0, 19.0],
            "MgO": [5.0, 6.0, 25.0, 26.0],
            "Nb": [1.0, 10.0, 100.0, 1000.0],
        }
    )


def test_shared_ranges_follow_variable_not_panel_position() -> None:
    from petrolab.multi_panel_plotting import panel_axis_limits

    panels = [
        {"x": "TiO2", "y": "Al2O3", "log_x": False, "log_y": False},
        {"x": "TiO2", "y": "MgO", "log_x": False, "log_y": False},
        {"x": "MgO", "y": "TiO2", "log_x": False, "log_y": False},
    ]
    limits = panel_axis_limits(_frame(), panels, mode="shared")
    assert limits[0]["x"] == limits[1]["x"]
    assert limits[0]["x"] == limits[2]["y"]
    assert limits[0]["y"] != limits[1]["y"]
    assert limits[1]["y"] == limits[2]["x"]


def test_fit_selection_zooms_without_filtering_dataframe() -> None:
    from petrolab.multi_panel_plotting import panel_axis_limits

    frame = _frame()
    original_ids = frame["_analysis_id"].tolist()
    panels = [{"x": "TiO2", "y": "MgO", "log_x": False, "log_y": False}]
    limits = panel_axis_limits(frame, panels, mode="focus", focus_ids=["a1", "a2"])
    xlim = limits[0]["x"]
    ylim = limits[0]["y"]
    assert xlim is not None and ylim is not None
    assert xlim[0] < 1.0 and xlim[1] > 2.0 and xlim[1] < 8.0
    assert ylim[0] < 5.0 and ylim[1] > 6.0 and ylim[1] < 25.0
    assert frame["_analysis_id"].tolist() == original_ids
    assert len(frame) == 4


def test_log_ranges_remain_positive_and_plotly_converts_to_log10() -> None:
    from petrolab.multi_panel_plotting import panel_axis_limits
    from petrolab.ui.linked_panels import _plotly_axis_range

    frame = _frame()
    panels = [{"x": "Nb", "y": "TiO2", "log_x": True, "log_y": False}]
    limits = panel_axis_limits(frame, panels, mode="shared")
    xlim = limits[0]["x"]
    assert xlim is not None and xlim[0] > 0 and xlim[1] > xlim[0]
    plotly_range = _plotly_axis_range(xlim, log=True)
    assert plotly_range is not None
    assert math.isclose(plotly_range[0], math.log10(xlim[0]))
    assert math.isclose(plotly_range[1], math.log10(xlim[1]))


def test_independent_and_empty_focus_leave_autoscale_unforced() -> None:
    from petrolab.multi_panel_plotting import panel_axis_limits

    panels = [{"x": "TiO2", "y": "MgO", "log_x": False, "log_y": False}]
    independent = panel_axis_limits(_frame(), panels, mode="independent")
    empty_focus = panel_axis_limits(_frame(), panels, mode="focus", focus_ids=[])
    assert independent == [{"x": None, "y": None}]
    assert empty_focus == [{"x": None, "y": None}]


def main() -> None:
    test_shared_ranges_follow_variable_not_panel_position()
    test_fit_selection_zooms_without_filtering_dataframe()
    test_log_ranges_remain_positive_and_plotly_converts_to_log10()
    test_independent_and_empty_focus_leave_autoscale_unforced()
    print("v0.15.8 multi-panel axis ranges: OK")


if __name__ == "__main__":
    main()
