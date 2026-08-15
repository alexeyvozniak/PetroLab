from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from petrolab.user_derived import evaluate_expression


def test_sum_of_oxides_keeps_wt_percent_unit() -> None:
    frame = pd.DataFrame({"Na2O": [3.0, 4.5], "K2O": [5.0, 2.5]})
    result = evaluate_expression(frame, "Na2O + K2O")
    assert result.unit == "wt%"
    assert result.dependencies == ("Na2O", "K2O")
    assert result.values.tolist() == pytest.approx([8.0, 7.0])


def test_trace_element_aliases_resolve_canonical_unit_columns() -> None:
    frame = pd.DataFrame({
        "La [µg/g]": [60.0, 30.0, np.nan],
        "Yb [µg/g]": [2.0, 0.0, 1.0],
    })
    result = evaluate_expression(frame, "La / Yb")
    assert result.unit == "1"
    assert result.dependencies == ("La [µg/g]", "Yb [µg/g]")
    assert result.values.iloc[0] == pytest.approx(30.0)
    assert np.isnan(result.values.iloc[1])
    assert np.isnan(result.values.iloc[2])
    assert result.warnings


def test_exact_backtick_column_reference_is_supported() -> None:
    frame = pd.DataFrame({"La [µg/g]": [10.0], "Yb [µg/g]": [2.0]})
    result = evaluate_expression(frame, "`La [µg/g]` / `Yb [µg/g]`")
    assert result.unit == "1"
    assert result.values.iloc[0] == pytest.approx(5.0)


def test_multi_component_expression_and_parentheses() -> None:
    frame = pd.DataFrame({
        "La [µg/g]": [10.0],
        "Ce [µg/g]": [20.0],
        "Pr [µg/g]": [5.0],
        "Yb [µg/g]": [2.5],
    })
    result = evaluate_expression(frame, "(La + Ce + Pr) / Yb")
    assert result.unit == "1"
    assert result.values.iloc[0] == pytest.approx(14.0)
    assert len(result.dependencies) == 4


def test_incompatible_addition_is_rejected() -> None:
    frame = pd.DataFrame({"SiO2": [50.0], "La [µg/g]": [40.0]})
    with pytest.raises(ValueError, match="Несовместимые единицы"):
        evaluate_expression(frame, "SiO2 + La")


def test_apfu_mg_number_is_dimensionless() -> None:
    frame = pd.DataFrame({"apfu_Mg": [2.5], "apfu_Fe2": [1.0]})
    result = evaluate_expression(frame, "apfu_Mg / (apfu_Mg + apfu_Fe2)")
    assert result.unit == "1"
    assert result.values.iloc[0] == pytest.approx(2.5 / 3.5)


def test_numeric_scaling_preserves_unit() -> None:
    frame = pd.DataFrame({"SiO2": [0.5, 0.8]})
    result = evaluate_expression(frame, "100 * SiO2")
    assert result.unit == "wt%"
    assert result.values.tolist() == pytest.approx([50.0, 80.0])


def test_python_calls_and_attributes_are_not_allowed() -> None:
    frame = pd.DataFrame({"SiO2": [50.0]})
    with pytest.raises(ValueError, match="неподдерживаемую операцию"):
        evaluate_expression(frame, "__import__('os').system('echo unsafe')")


def test_identity_columns_cannot_be_used_as_numeric_inputs() -> None:
    frame = pd.DataFrame({"_analysis_id": ["abc"], "SiO2": [50.0]})
    with pytest.raises(ValueError, match="Служебные identity-поля"):
        evaluate_expression(frame, "_analysis_id + 1")
