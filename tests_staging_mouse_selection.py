from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from petrolab.import_staging import assign_value_to_rows
from petrolab.ui.staging_editor import selected_positions_from_event


def test_rectangular_cells_promote_to_analysis_rows() -> None:
    event = SimpleNamespace(
        selection=SimpleNamespace(
            rows=[],
            cells=[
                (2, "SiO2"),
                (2, "MgO"),
                (3, "SiO2"),
                (3, "MgO"),
                (4, "SiO2"),
                (4, "MgO"),
                (5, "SiO2"),
                (5, "MgO"),
            ],
        )
    )
    assert selected_positions_from_event(event, row_count=10) == [2, 3, 4, 5]


def test_row_headers_and_cells_are_deduplicated() -> None:
    event = {
        "selection": {
            "rows": [1, 2, 7],
            "cells": [(2, "SiO2"), (3, "Al2O3"), (7, "MgO"), (999, "MgO")],
        }
    }
    assert selected_positions_from_event(event, row_count=8) == [1, 2, 3, 7]


def test_sample_and_mineral_can_be_assigned_to_one_mouse_range() -> None:
    frame = pd.DataFrame(
        {
            "Point": [f"P-{index}" for index in range(12)],
            "SiO2": [40.0 + index / 10 for index in range(12)],
        }
    )
    selected = list(range(1, 11))
    result = assign_value_to_rows(frame, selected, field="Sample", value="19")
    result = assign_value_to_rows(result, selected, field="Mineral", value="phlogopite")

    assert result.loc[1:10, "Sample"].tolist() == ["19"] * 10
    assert result.loc[1:10, "Mineral"].tolist() == ["phlogopite"] * 10
    assert pd.isna(result.loc[0, "Sample"])
    assert pd.isna(result.loc[11, "Mineral"])


def test_ui_contract_exposes_mouse_range_as_default() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parent / "petrolab" / "ui" / "staging_editor.py").read_text(encoding="utf-8")
    assert 'default="Выделить мышью"' in source
    assert 'selection_mode=["multi-row", "multi-cell"]' in source
    assert 'on_select="rerun"' in source
    assert "PetroLab выберет все строки, которых коснулся диапазон" in source


def main() -> None:
    test_rectangular_cells_promote_to_analysis_rows()
    test_row_headers_and_cells_are_deduplicated()
    test_sample_and_mineral_can_be_assigned_to_one_mouse_range()
    test_ui_contract_exposes_mouse_range_as_default()
    print("PetroLab staging mouse range selection: OK")


if __name__ == "__main__":
    main()
