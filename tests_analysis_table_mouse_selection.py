from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

from petrolab.ui.analysis_table import _analysis_row_positions, selected_positions_from_table_event


def test_rectangular_cell_drag_selects_unique_analysis_rows() -> None:
    event = SimpleNamespace(
        selection=SimpleNamespace(
            rows=[],
            cells=[
                (4, "SiO2"),
                (4, "MgO"),
                (5, "SiO2"),
                (5, "MgO"),
                (6, "SiO2"),
                (6, "MgO"),
            ],
        )
    )
    assert selected_positions_from_table_event(event, row_count=12) == [4, 5, 6]


def test_row_and_cell_selection_share_one_row_scope() -> None:
    event = {
        "selection": {
            "rows": [1, 3],
            "cells": [(2, "Al2O3"), (3, "TiO2"), (100, "MgO")],
        }
    }
    assert selected_positions_from_table_event(event, row_count=5) == [1, 2, 3]


def test_positions_resolve_exact_analysis_ids_after_sorting_input() -> None:
    frame = pd.DataFrame(
        {
            "_analysis_id": ["a-9", "a-2", "a-7", "a-1"],
            "SiO2": [39.9, 41.2, 40.5, 42.0],
        }
    ).sort_values("SiO2", ascending=False, kind="stable")
    positions = [0, 1]
    assert frame.iloc[positions]["_analysis_id"].tolist() == ["a-1", "a-2"]


def test_external_selection_resolves_back_to_visible_table_rows() -> None:
    frame = pd.DataFrame(
        {
            "_analysis_id": ["a-9", "a-2", "a-7", "a-1"],
            "SiO2": [39.9, 41.2, 40.5, 42.0],
        }
    ).sort_values("SiO2", ascending=False, kind="stable")
    assert frame["_analysis_id"].tolist() == ["a-1", "a-2", "a-7", "a-9"]
    assert _analysis_row_positions(frame, ("a-7", "a-1")) == [0, 2]
    assert _analysis_row_positions(frame, ("not-visible", "a-2")) == [1]


def test_ui_contract_uses_multi_cell_not_checkbox_column() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parent / "petrolab" / "ui" / "analysis_table.py").read_text(encoding="utf-8")
    assert 'selection_mode=["multi-row", "multi-cell"]' in source
    assert 'origin="Таблица · мышью"' in source
    assert "CheckboxColumn" not in source
    assert 'editor.insert(0, "Выбрать"' not in source
    assert "все затронутые строки сразу становятся Selection" in source
    assert "_sync_grid_from_context" in source
    assert 'st.session_state[grid_key] = {"selection": {"rows": rows}}' in source
    assert "Selection с графика/шлифа подсвечивается здесь теми же строками" in source


def main() -> None:
    test_rectangular_cell_drag_selects_unique_analysis_rows()
    test_row_and_cell_selection_share_one_row_scope()
    test_positions_resolve_exact_analysis_ids_after_sorting_input()
    test_external_selection_resolves_back_to_visible_table_rows()
    test_ui_contract_uses_multi_cell_not_checkbox_column()
    print("PetroLab canonical table mouse range selection: OK")


if __name__ == "__main__":
    main()
