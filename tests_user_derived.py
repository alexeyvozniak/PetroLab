from __future__ import annotations

import math

import numpy as np
import pandas as pd

from petrolab.user_derived import evaluate_expression


def _close(left: float, right: float, tol: float = 1e-10) -> bool:
    return math.isclose(float(left), float(right), rel_tol=tol, abs_tol=tol)


def _expect_value_error(fragment: str, callback) -> None:
    try:
        callback()
    except ValueError as exc:
        assert fragment in str(exc), (fragment, str(exc))
    else:
        raise AssertionError(f"Expected ValueError containing: {fragment}")


def main() -> None:
    frame = pd.DataFrame({"Na2O": [3.0, 4.5], "K2O": [5.0, 2.5]})
    result = evaluate_expression(frame, "Na2O + K2O")
    assert result.unit == "wt%"
    assert result.dependencies == ("Na2O", "K2O")
    assert [_close(a, b) for a, b in zip(result.values, [8.0, 7.0])] == [True, True]

    frame = pd.DataFrame({
        "La [µg/g]": [60.0, 30.0, np.nan],
        "Yb [µg/g]": [2.0, 0.0, 1.0],
    })
    result = evaluate_expression(frame, "La / Yb")
    assert result.unit == "1"
    assert result.dependencies == ("La [µg/g]", "Yb [µg/g]")
    assert _close(result.values.iloc[0], 30.0)
    assert np.isnan(result.values.iloc[1])
    assert np.isnan(result.values.iloc[2])
    assert result.warnings

    frame = pd.DataFrame({"La [µg/g]": [10.0], "Yb [µg/g]": [2.0]})
    result = evaluate_expression(frame, "`La [µg/g]` / `Yb [µg/g]`")
    assert result.unit == "1"
    assert _close(result.values.iloc[0], 5.0)

    frame = pd.DataFrame({
        "La [µg/g]": [10.0],
        "Ce [µg/g]": [20.0],
        "Pr [µg/g]": [5.0],
        "Yb [µg/g]": [2.5],
    })
    result = evaluate_expression(frame, "(La + Ce + Pr) / Yb")
    assert result.unit == "1"
    assert _close(result.values.iloc[0], 14.0)
    assert len(result.dependencies) == 4

    frame = pd.DataFrame({"SiO2": [50.0], "La [µg/g]": [40.0]})
    _expect_value_error("Несовместимые единицы", lambda: evaluate_expression(frame, "SiO2 + La"))

    frame = pd.DataFrame({"apfu_Mg": [2.5], "apfu_Fe2": [1.0]})
    result = evaluate_expression(frame, "apfu_Mg / (apfu_Mg + apfu_Fe2)")
    assert result.unit == "1"
    assert _close(result.values.iloc[0], 2.5 / 3.5)

    frame = pd.DataFrame({"SiO2": [0.5, 0.8]})
    result = evaluate_expression(frame, "100 * SiO2")
    assert result.unit == "wt%"
    assert _close(result.values.iloc[0], 50.0)
    assert _close(result.values.iloc[1], 80.0)

    frame = pd.DataFrame({"SiO2": [50.0]})
    _expect_value_error(
        "неподдерживаемую операцию",
        lambda: evaluate_expression(frame, "__import__('os').system('echo unsafe')"),
    )

    frame = pd.DataFrame({"_analysis_id": ["abc"], "SiO2": [50.0]})
    _expect_value_error(
        "Служебные identity-поля",
        lambda: evaluate_expression(frame, "_analysis_id + 1"),
    )

    frame = pd.DataFrame({"ratio": [2.0, 3.0]})
    frame.attrs["derived_units"] = {"ratio": "1"}
    result = evaluate_expression(frame, "ratio + 1")
    assert result.unit == "1"
    assert _close(result.values.iloc[0], 3.0)
    assert _close(result.values.iloc[1], 4.0)

    print("user-derived field tests: OK")


if __name__ == "__main__":
    main()
