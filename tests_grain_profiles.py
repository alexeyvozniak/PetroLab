from __future__ import annotations

import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from petrolab.grain_profiles import (
    build_grain_profile_figure,
    figure_bytes,
    grain_profile_recipe,
    prepare_grain_profile,
    recipe_json_bytes,
)


def main() -> None:
    frame = pd.DataFrame({
        "_analysis_id": [f"a{index}" for index in range(1, 6)],
        "Point": ["P-5", "P-2", "P-4", "P-1", "P-3"],
        "Order": [5, 2, 4, 1, 3],
        "Distance_um": [40.0, 10.0, 30.0, 0.0, 20.0],
        "X": [40.0, 10.0, 30.0, 0.0, 20.0],
        "Y": [0.0, 0.0, 0.0, 0.0, 0.0],
        "Frame": ["grain-1"] * 5,
        "MgO": [10.0, 12.0, np.nan, 15.0, 13.0],
        "FeO": [8.0, 7.0, 7.5, 6.0, 6.5],
    })

    exact = ["a4", "a2", "a5", "a3", "a1"]
    result = prepare_grain_profile(frame, analysis_ids=exact, order_mode="selection")
    assert result.dataframe["_analysis_id"].tolist() == exact
    assert result.dataframe["_profile_order"].tolist() == [1, 2, 3, 4, 5]
    assert result.dataframe["_profile_x"].tolist() == [0.0, 1.0, 2.0, 3.0, 4.0]

    explicit = prepare_grain_profile(frame, order_mode="explicit", order_column="Order")
    assert explicit.dataframe["Order"].tolist() == [1, 2, 3, 4, 5]
    assert explicit.dataframe["_analysis_id"].tolist() == ["a4", "a2", "a5", "a3", "a1"]

    labels = prepare_grain_profile(frame, order_mode="label_number", label_column="Point")
    assert labels.dataframe["Point"].tolist() == ["P-1", "P-2", "P-3", "P-4", "P-5"]

    distance = prepare_grain_profile(frame, order_mode="distance", distance_column="Distance_um")
    assert distance.dataframe["Distance_um"].tolist() == [0.0, 10.0, 20.0, 30.0, 40.0]
    assert distance.dataframe["_profile_x"].tolist() == [0.0, 10.0, 20.0, 30.0, 40.0]

    normalized = prepare_grain_profile(
        frame,
        order_mode="distance",
        distance_column="Distance_um",
        normalize_distance=True,
    )
    assert np.allclose(normalized.dataframe["_profile_x"], [0.0, 0.25, 0.5, 0.75, 1.0])

    reversed_profile = prepare_grain_profile(
        frame,
        order_mode="distance",
        distance_column="Distance_um",
        reverse=True,
    )
    assert reversed_profile.dataframe["_analysis_id"].tolist() == ["a1", "a3", "a5", "a2", "a4"]
    assert reversed_profile.dataframe["_profile_x"].tolist() == [0.0, 10.0, 20.0, 30.0, 40.0]

    geometry = pd.DataFrame({
        "_analysis_id": ["g1", "g2", "g3"],
        "Order": [1, 2, 3],
        "X": [0.0, 3.0, 3.0],
        "Y": [0.0, 0.0, 4.0],
        "Frame": ["image-17"] * 3,
        "MgO": [15.0, 13.0, 11.0],
    })
    geometric = prepare_grain_profile(
        geometry,
        order_mode="geometry",
        order_column="Order",
        x_column="X",
        y_column="Y",
        coordinate_frame_column="Frame",
    )
    assert np.allclose(geometric.dataframe["_profile_x"], [0.0, 3.0, 7.0])

    mixed_frames = geometry.copy()
    mixed_frames.loc[2, "Frame"] = "image-18"
    try:
        prepare_grain_profile(
            mixed_frames,
            order_mode="geometry",
            order_column="Order",
            x_column="X",
            y_column="Y",
            coordinate_frame_column="Frame",
        )
    except ValueError as exc:
        assert "одной системы координат" in str(exc)
    else:
        raise AssertionError("Geometry across unrelated images must be refused")

    blank_frame = geometry.copy()
    blank_frame.loc[1, "Frame"] = ""
    try:
        prepare_grain_profile(
            blank_frame,
            order_mode="geometry",
            order_column="Order",
            x_column="X",
            y_column="Y",
            coordinate_frame_column="Frame",
        )
    except ValueError as exc:
        assert "одной системы координат" in str(exc)
    else:
        raise AssertionError("Geometry with a blank coordinate-frame id must be refused")

    duplicate_order = frame.copy()
    duplicate_order.loc[0, "Order"] = 1
    try:
        prepare_grain_profile(duplicate_order, order_mode="explicit", order_column="Order")
    except ValueError as exc:
        assert "неоднозначен" in str(exc)
    else:
        raise AssertionError("Duplicate physical ordering must fail")

    try:
        prepare_grain_profile(frame, analysis_ids=["a4", "missing"], order_mode="selection")
    except ValueError as exc:
        assert "missing" in str(exc)
    else:
        raise AssertionError("Exact selection must not silently lose missing analysis ids")

    # Missing chemistry remains NaN and therefore a plotted gap, never a zero.
    explicit_mg = pd.to_numeric(explicit.dataframe["MgO"], errors="coerce")
    assert explicit_mg.isna().sum() == 1
    assert not (explicit_mg.fillna(-999.0) == 0.0).any()

    figure = build_grain_profile_figure(
        explicit,
        ["MgO", "FeO"],
        zones=[
            {"start": 0.0, "end": 1.0, "label": "core"},
            {"start": 3.0, "end": 4.0, "label": "rim"},
        ],
    )
    assert len(figure.axes[0].lines) == 2
    assert any(text.get_text() == "core" for text in figure.axes[0].texts)
    assert len(figure_bytes(figure, "png", 300)) > 1000
    assert b"<svg" in figure_bytes(figure, "svg", 300)[:1000]
    plt.close(figure)

    recipe = grain_profile_recipe(explicit, y_columns=["MgO", "FeO"])
    payload = json.loads(recipe_json_bytes(recipe).decode("utf-8"))
    assert payload["kind"] == "grain_profile"
    assert payload["analysis_ids"] == ["a4", "a2", "a5", "a3", "a1"]

    hundred = pd.DataFrame({
        "_analysis_id": [f"p{index}" for index in range(100)],
        "Order": list(range(100)),
        "MgO": np.linspace(15.0, 5.0, 100),
    })
    hundred_result = prepare_grain_profile(hundred, order_mode="explicit", order_column="Order")
    assert len(hundred_result.dataframe) == 100
    assert hundred_result.dataframe["_analysis_id"].iloc[0] == "p0"
    assert hundred_result.dataframe["_analysis_id"].iloc[-1] == "p99"

    print("grain profile tests: OK")


if __name__ == "__main__":
    main()
