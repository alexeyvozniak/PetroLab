from __future__ import annotations

import pandas as pd


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Панель": 1,
                "X": "Al2O3",
                "Y": "TiO2",
                "Название": "Ti–Al",
                "log X": False,
                "log Y": False,
                "Порядок": 1,
                "Убрать": False,
                "Дублировать": False,
            },
            {
                "Панель": 2,
                "X": "MgO",
                "Y": "FeOt",
                "Название": "Mg–Fe",
                "log X": True,
                "log Y": False,
                "Порядок": 2,
                "Убрать": False,
                "Дублировать": False,
            },
            {
                "Панель": 3,
                "X": "Nb",
                "Y": "Ta",
                "Название": "Nb–Ta",
                "log X": False,
                "log Y": True,
                "Порядок": 3,
                "Убрать": False,
                "Дублировать": False,
            },
        ]
    )


def test_remove_preserves_other_panel_specs() -> None:
    from petrolab.ui.panel_manager import _panel_rows_after_actions

    source = _frame()
    source.loc[1, "Убрать"] = True
    result, truncated = _panel_rows_after_actions(source)
    assert result is not None
    assert truncated is False
    assert len(result) == 2
    assert result["Название"].tolist() == ["Ti–Al", "Nb–Ta"]
    assert result["X"].tolist() == ["Al2O3", "Nb"]
    assert result["Y"].tolist() == ["TiO2", "Ta"]
    assert result["log Y"].tolist() == [False, True]
    assert result["Панель"].tolist() == [1, 2]
    assert result["Порядок"].tolist() == [1, 2]


def test_duplicate_keeps_scientific_spec_and_creates_independent_copy() -> None:
    from petrolab.ui.panel_manager import _panel_rows_after_actions

    source = _frame()
    source.loc[0, "Дублировать"] = True
    result, truncated = _panel_rows_after_actions(source)
    assert result is not None
    assert truncated is False
    assert len(result) == 4
    assert result.iloc[0]["X"] == result.iloc[1]["X"] == "Al2O3"
    assert result.iloc[0]["Y"] == result.iloc[1]["Y"] == "TiO2"
    assert result.iloc[1]["Название"] == "Ti–Al · копия"
    assert bool(result.iloc[1]["Дублировать"]) is False
    assert result["Порядок"].tolist() == [1, 2, 3, 4]

    # Editing the returned copy does not mutate its source row.
    result.loc[1, "Y"] = "FeOt"
    assert result.loc[0, "Y"] == "TiO2"
    assert result.loc[1, "Y"] == "FeOt"


def test_cannot_remove_every_panel() -> None:
    from petrolab.ui.panel_manager import _panel_rows_after_actions

    source = _frame()
    source["Убрать"] = True
    result, truncated = _panel_rows_after_actions(source)
    assert result is None
    assert truncated is False


def test_duplicate_respects_ten_panel_limit() -> None:
    from petrolab.ui.panel_manager import _panel_rows_after_actions

    source = _frame()
    source["Дублировать"] = True
    result, truncated = _panel_rows_after_actions(source, maximum=4)
    assert result is not None
    assert len(result) == 4
    assert truncated is True


def main() -> None:
    test_remove_preserves_other_panel_specs()
    test_duplicate_keeps_scientific_spec_and_creates_independent_copy()
    test_cannot_remove_every_panel()
    test_duplicate_respects_ten_panel_limit()
    print("v0.15.8 panel manager structure: OK")


if __name__ == "__main__":
    main()
