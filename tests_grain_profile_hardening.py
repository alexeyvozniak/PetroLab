from __future__ import annotations

import numpy as np
import pandas as pd

from petrolab.grain_profile_groups import (
    build_grouped_grain_profile_figure,
    grouped_grain_profile_recipe,
    grouped_profile_dataframe,
    prepare_grouped_grain_profiles,
)
from petrolab.grain_profiles import build_grain_profile_figure, prepare_grain_profile
from petrolab.ui.pages.grain_profile import _exact_order, _single_profile_grain_guard


def _expect_value_error(callable_obj, text: str) -> None:
    try:
        callable_obj()
    except ValueError as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError(f"Expected ValueError containing: {text}")


def main() -> None:
    frame = pd.DataFrame({
        "_analysis_id": ["a1", "a2", "a3"],
        "Order": [1.0, 2.0, 3.0],
        "X": [0.0, 1.0, 2.0],
        "Y": [0.0, 0.0, 0.0],
        "Frame": ["img-1"] * 3,
        "MgO": [15.0, 14.0, 13.0],
    })

    ordered, missing = _exact_order(frame, ["a3", "a1", "a2"])
    assert missing == []
    assert ordered["_analysis_id"].tolist() == ["a3", "a1", "a2"]
    ordered, missing = _exact_order(frame, ["a2", "missing", "a1"])
    assert ordered["_analysis_id"].tolist() == ["a2", "a1"]
    assert missing == ["missing"]

    bad_order = frame.copy()
    bad_order.loc[1, "Order"] = np.inf
    _expect_value_error(
        lambda: prepare_grain_profile(bad_order, order_mode="explicit", order_column="Order"),
        "бесконечные/некорректные",
    )

    bad_geometry = frame.copy()
    bad_geometry.loc[2, "X"] = -np.inf
    _expect_value_error(
        lambda: prepare_grain_profile(
            bad_geometry,
            order_mode="geometry",
            order_column="Order",
            x_column="X",
            y_column="Y",
            coordinate_frame_column="Frame",
        ),
        "бесконечные/некорректные",
    )

    result = prepare_grain_profile(frame, order_mode="explicit", order_column="Order")
    one_bad = result.dataframe.copy()
    one_bad.loc[1, "MgO"] = np.inf
    result_with_gap = type(result)(
        dataframe=one_bad,
        x_label=result.x_label,
        order_mode=result.order_mode,
        normalized=result.normalized,
        reversed_direction=result.reversed_direction,
    )
    figure = build_grain_profile_figure(result_with_gap, ["MgO"])
    y = figure.axes[0].lines[0].get_ydata()
    assert np.isnan(y[1]), "Infinite derived values must become a plotted gap, not a real point"

    all_bad = result.dataframe.copy()
    all_bad["MgO"] = np.inf
    all_bad_result = type(result)(
        dataframe=all_bad,
        x_label=result.x_label,
        order_mode=result.order_mode,
        normalized=result.normalized,
        reversed_direction=result.reversed_direction,
    )
    _expect_value_error(
        lambda: build_grain_profile_figure(all_bad_result, ["MgO"]),
        "нет конечных числовых значений",
    )

    # Two grains must never be silently concatenated into one traverse when a
    # canonical grain identity column is available.
    multi = pd.DataFrame({
        "_analysis_id": ["g1-2", "g2-1", "g1-1", "g2-2"],
        "Grain": ["G1", "G2", "G1", "G2"],
        "Point": ["P-2", "P-1", "P-1", "P-2"],
        "Distance_um": [20.0, 0.0, 0.0, 30.0],
        "X": [20.0, 100.0, 0.0, 130.0],
        "Y": [0.0, 50.0, 0.0, 50.0],
        "Frame": ["image-g1", "image-g2", "image-g1", "image-g2"],
        "MgO": [11.0, 14.0, 15.0, 10.0],
    })
    assert _single_profile_grain_guard(multi, multi["_analysis_id"].tolist()) == "Grain"
    grouped = prepare_grouped_grain_profiles(
        multi,
        group_column="Grain",
        analysis_ids=["g2-1", "g1-2", "g1-1", "g2-2"],
        order_mode="label_number",
        label_column="Point",
        normalize_distance=True,
    )
    assert [name for name, _ in grouped.profiles] == ["G2", "G1"]
    g2 = grouped.profiles[0][1].dataframe
    g1 = grouped.profiles[1][1].dataframe
    assert g2["_analysis_id"].tolist() == ["g2-1", "g2-2"]
    assert g1["_analysis_id"].tolist() == ["g1-1", "g1-2"]
    assert np.allclose(g1["_profile_x"], [0.0, 1.0])
    assert np.allclose(g2["_profile_x"], [0.0, 1.0])
    combined = grouped_profile_dataframe(grouped)
    assert combined["_profile_group"].tolist() == ["G2", "G2", "G1", "G1"]
    overlay = build_grouped_grain_profile_figure(grouped, ["MgO"], display_mode="overlay")
    assert len(overlay.axes) == 1
    assert len(overlay.axes[0].lines) == 2
    assert {line.get_label() for line in overlay.axes[0].lines} == {"G1", "G2"}
    facets = build_grouped_grain_profile_figure(grouped, ["MgO"], display_mode="facets")
    assert len(facets.axes) == 2
    recipe = grouped_grain_profile_recipe(grouped, y_columns=["MgO"], display_mode="overlay")
    assert recipe["kind"] == "grain_profile_grouped"
    assert [group["name"] for group in recipe["groups"]] == ["G2", "G1"]

    # Geometry is checked separately per grain, so different image frames are
    # allowed across grains but never inside one grain.
    geometric = prepare_grouped_grain_profiles(
        multi,
        group_column="Grain",
        order_mode="label_number",
        label_column="Point",
        x_column="X",
        y_column="Y",
        coordinate_frame_column="Frame",
        normalize_distance=False,
    )
    assert len(geometric.profiles) == 2
    broken_frame = multi.copy()
    broken_frame.loc[broken_frame["_analysis_id"].eq("g1-2"), "Frame"] = "another-image"
    _expect_value_error(
        lambda: prepare_grouped_grain_profiles(
            broken_frame,
            group_column="Grain",
            order_mode="geometry",
            order_column="Distance_um",
            x_column="X",
            y_column="Y",
            coordinate_frame_column="Frame",
        ),
        "одной системы координат",
    )

    print("grain profile hardening tests: OK")


if __name__ == "__main__":
    main()
