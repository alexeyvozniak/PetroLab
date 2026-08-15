from __future__ import annotations

import math
import os
import tempfile

# Isolate the full SQLite/runtime integration before importing PetroLab.  The
# package reads PETROLAB_DATA_DIR at import time.
_TEST_DATA = tempfile.TemporaryDirectory(prefix="petrolab-user-derived-")
os.environ["PETROLAB_DATA_DIR"] = _TEST_DATA.name

import numpy as np
import pandas as pd

from petrolab import derived
from petrolab.db import add_dataset, create_project, replace_dataset_rows
from petrolab.repositories import rock_repository
from petrolab.user_derived import (
    evaluate_expression,
    save_dataset_field,
    save_rock_project_field,
)


def _close(left: float, right: float, tol: float = 1e-10) -> bool:
    return math.isclose(float(left), float(right), rel_tol=tol, abs_tol=tol)


def _expect_value_error(fragment: str, callback) -> None:
    try:
        callback()
    except ValueError as exc:
        assert fragment in str(exc), (fragment, str(exc))
    else:
        raise AssertionError(f"Expected ValueError containing: {fragment}")


def _test_expression_engine() -> None:
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


def _test_dataset_persistence_and_live_recalculation() -> None:
    project_id = create_project("Formula Builder analysis test")
    dataset_id = add_dataset(
        project_id=project_id,
        name="mica chemistry",
        mineral_key="mica",
        source_filename="formula-test.xlsx",
        source_sheet="Sheet1",
        source_sha256="formula-test",
        csv_path="",
        row_count=2,
    )
    source = pd.DataFrame({
        "Sample": ["A", "B"],
        "SiO2": [50.0, 40.0],
        "Na2O": [3.0, 4.0],
        "K2O": [5.0, 2.0],
        "La [µg/g]": [60.0, 30.0],
        "Yb [µg/g]": [2.0, 3.0],
    })
    replace_dataset_rows(dataset_id, source, source_rows=[2, 3])

    raw = derived.load_dataset_with_derived(dataset_id, include_meta=True)
    preview = evaluate_expression(raw, "Na2O + K2O")
    save_dataset_field(
        dataset_id,
        name="Alkalis",
        expression="Na2O + K2O",
        unit=preview.unit,
        dependencies=preview.dependencies,
        description="Total alkalis",
    )

    calculated = derived.load_dataset_with_derived(dataset_id, include_meta=True)
    assert calculated["Alkalis"].tolist() == [8.0, 6.0]
    assert calculated.attrs["derived_units"]["Alkalis"] == "wt%"

    chained = evaluate_expression(calculated, "Alkalis / SiO2")
    assert chained.unit == "1"
    save_dataset_field(
        dataset_id,
        name="AlkaliIndex",
        expression="Alkalis / SiO2",
        unit=chained.unit,
        dependencies=chained.dependencies,
        description="Dynamic formula depending on another dynamic formula",
    )
    calculated = derived.load_dataset_with_derived(dataset_id, include_meta=True)
    assert _close(calculated.loc[0, "AlkaliIndex"], 8.0 / 50.0)
    assert _close(calculated.loc[1, "AlkaliIndex"], 6.0 / 40.0)

    # A persisted definition must never be allowed to shadow real chemistry,
    # even if it was inserted through the lower-level API rather than the UI.
    save_dataset_field(
        dataset_id,
        name="SiO2",
        expression="Na2O + K2O",
        unit="wt%",
        dependencies=("Na2O", "K2O"),
        description="intentional collision test",
    )
    collision_safe = derived.load_dataset_with_derived(dataset_id, include_meta=True)
    assert collision_safe["SiO2"].tolist() == [50.0, 40.0]
    assert any("SiO2" in warning and "занято" in warning for warning in collision_safe.attrs["user_derived_warnings"])

    # Change the source chemistry.  The formula definition survives and values
    # change immediately; no stale materialized snapshot is reused.
    changed = source.copy()
    changed.loc[0, "K2O"] = 7.0
    changed.loc[1, "Yb [µg/g]"] = 0.0
    replace_dataset_rows(dataset_id, changed, source_rows=[2, 3])
    refreshed = derived.load_dataset_with_derived(dataset_id, include_meta=True)
    assert refreshed["Alkalis"].tolist() == [10.0, 6.0]
    assert _close(refreshed.loc[0, "AlkaliIndex"], 10.0 / 50.0)
    assert refreshed["SiO2"].tolist() == [50.0, 40.0]


def _test_whole_rock_persistence() -> None:
    project_id = create_project("Formula Builder whole-rock test")
    rock_id = rock_repository.create_rock(project_id, "R-1", massif="Test massif", lithology="lamprophyre")
    rock_repository.upsert_composition_values(
        rock_id,
        [
            {"analyte": "Na2O", "value": 3.0, "unit": "wt%"},
            {"analyte": "K2O", "value": 5.0, "unit": "wt%"},
            {"analyte": "La", "value": 60.0, "unit": "ppm"},
            {"analyte": "Yb", "value": 2.0, "unit": "ppm"},
        ],
    )
    source = rock_repository.composition_wide(project_id)
    assert "La [µg/g]" in source.columns
    preview = evaluate_expression(source, "La / Yb")
    assert preview.unit == "1"
    save_rock_project_field(
        project_id,
        name="La/Yb",
        expression="La / Yb",
        unit=preview.unit,
        dependencies=preview.dependencies,
        description="Whole-rock trace-element ratio",
    )
    preview_alkalis = evaluate_expression(source, "Na2O + K2O")
    save_rock_project_field(
        project_id,
        name="Na2O+K2O",
        expression="Na2O + K2O",
        unit=preview_alkalis.unit,
        dependencies=preview_alkalis.dependencies,
        description="Whole-rock total alkalis",
    )

    calculated = rock_repository.composition_wide(project_id)
    assert _close(calculated.loc[0, "La/Yb"], 30.0)
    assert _close(calculated.loc[0, "Na2O+K2O"], 8.0)

    rock_repository.upsert_composition_values(
        rock_id,
        [
            {"analyte": "Na2O", "value": 4.0, "unit": "wt%"},
            {"analyte": "K2O", "value": 6.0, "unit": "wt%"},
            {"analyte": "La", "value": 80.0, "unit": "ppm"},
            {"analyte": "Yb", "value": 4.0, "unit": "ppm"},
        ],
    )
    refreshed = rock_repository.composition_wide(project_id)
    assert _close(refreshed.loc[0, "La/Yb"], 20.0)
    assert _close(refreshed.loc[0, "Na2O+K2O"], 10.0)


def main() -> None:
    _test_expression_engine()
    _test_dataset_persistence_and_live_recalculation()
    _test_whole_rock_persistence()
    print("user-derived field tests: OK")


if __name__ == "__main__":
    try:
        main()
    finally:
        _TEST_DATA.cleanup()
