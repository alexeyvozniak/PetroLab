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


def test_shared_x_only_synchronizes_same_variable_x_axes() -> None:
    from petrolab.multi_panel_plotting import panel_axis_limits

    panels = [
        {"x": "TiO2", "y": "Al2O3", "log_x": False, "log_y": False},
        {"x": "TiO2", "y": "MgO", "log_x": False, "log_y": False},
        {"x": "MgO", "y": "TiO2", "log_x": False, "log_y": False},
    ]
    limits = panel_axis_limits(_frame(), panels, mode="shared_x")
    assert limits[0]["x"] == limits[1]["x"]
    assert limits[0]["x"] is not None
    assert limits[2]["x"] is not None
    assert limits[0]["x"] != limits[2]["x"], "different X variables must not share a numeric range"
    assert all(item["y"] is None for item in limits), "shared X must leave every Y axis automatic"


def test_shared_y_only_synchronizes_same_variable_y_axes() -> None:
    from petrolab.multi_panel_plotting import panel_axis_limits

    panels = [
        {"x": "TiO2", "y": "Al2O3", "log_x": False, "log_y": False},
        {"x": "Nb", "y": "Al2O3", "log_x": True, "log_y": False},
        {"x": "MgO", "y": "TiO2", "log_x": False, "log_y": False},
    ]
    limits = panel_axis_limits(_frame(), panels, mode="shared_y")
    assert limits[0]["y"] == limits[1]["y"]
    assert limits[0]["y"] is not None
    assert limits[2]["y"] is not None
    assert limits[0]["y"] != limits[2]["y"], "different Y variables must not share a numeric range"
    assert all(item["x"] is None for item in limits), "shared Y must leave every X axis automatic"


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


def test_manual_range_overrides_only_its_panel_axis() -> None:
    from petrolab.multi_panel_plotting import panel_axis_limits

    panels = [
        {
            "x": "TiO2", "y": "Al2O3", "log_x": False, "log_y": False,
            "x_min": 0.0, "x_max": 5.0, "y_min": None, "y_max": None,
        },
        {
            "x": "TiO2", "y": "MgO", "log_x": False, "log_y": False,
            "x_min": None, "x_max": None, "y_min": 0.0, "y_max": 30.0,
        },
    ]
    limits = panel_axis_limits(_frame(), panels, mode="shared")
    assert limits[0]["x"] == (0.0, 5.0)
    assert limits[1]["x"] != (0.0, 5.0), "manual override must not change sibling panel"
    assert limits[1]["y"] == (0.0, 30.0)
    assert limits[0]["y"] != (0.0, 30.0)


def test_manual_range_still_overrides_shared_x_or_shared_y() -> None:
    from petrolab.multi_panel_plotting import panel_axis_limits

    panels = [
        {
            "x": "TiO2", "y": "Al2O3", "log_x": False, "log_y": False,
            "x_min": 0.0, "x_max": 4.0,
        },
        {"x": "TiO2", "y": "Al2O3", "log_x": False, "log_y": False},
    ]
    x_limits = panel_axis_limits(_frame(), panels, mode="shared_x")
    assert x_limits[0]["x"] == (0.0, 4.0)
    assert x_limits[1]["x"] != (0.0, 4.0)
    assert x_limits[0]["y"] is None and x_limits[1]["y"] is None


def test_manual_range_works_even_when_global_mode_is_auto_or_data_is_empty() -> None:
    from petrolab.multi_panel_plotting import panel_axis_limits

    panel = {
        "x": "TiO2", "y": "MgO", "log_x": False, "log_y": False,
        "x_min": 1.5, "x_max": 7.5, "y_min": None, "y_max": None,
    }
    assert panel_axis_limits(_frame(), [panel], mode="independent")[0]["x"] == (1.5, 7.5)
    assert panel_axis_limits(_frame().iloc[0:0], [panel], mode="shared")[0]["x"] == (1.5, 7.5)


def test_invalid_or_nonpositive_log_manual_range_does_not_override_safe_auto() -> None:
    from petrolab.multi_panel_plotting import panel_axis_limits

    panel = {
        "x": "Nb", "y": "TiO2", "log_x": True, "log_y": False,
        "x_min": -1.0, "x_max": 100.0,
    }
    limits = panel_axis_limits(_frame(), [panel], mode="shared")
    assert limits[0]["x"] is not None
    assert limits[0]["x"][0] > 0


def main() -> None:
    test_shared_ranges_follow_variable_not_panel_position()
    test_shared_x_only_synchronizes_same_variable_x_axes()
    test_shared_y_only_synchronizes_same_variable_y_axes()
    test_fit_selection_zooms_without_filtering_dataframe()
    test_log_ranges_remain_positive_and_plotly_converts_to_log10()
    test_independent_and_empty_focus_leave_autoscale_unforced()
    test_manual_range_overrides_only_its_panel_axis()
    test_manual_range_still_overrides_shared_x_or_shared_y()
    test_manual_range_works_even_when_global_mode_is_auto_or_data_is_empty()
    test_invalid_or_nonpositive_log_manual_range_does_not_override_safe_auto()
    print("v0.15.8 multi-panel axis ranges: OK")


if __name__ == "__main__":
    main()
