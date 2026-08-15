from __future__ import annotations

import numpy as np
import pandas as pd

from petrolab.grain_profiles import build_grain_profile_figure, prepare_grain_profile
from petrolab.ui.pages.grain_profile import _exact_order


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

    print("grain profile hardening tests: OK")


if __name__ == "__main__":
    main()
