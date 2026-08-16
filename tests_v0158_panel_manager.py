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
                "X min": 0.0,
                "X max": 20.0,
                "Y min": None,
                "Y max": None,
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
                "X min": 0.1,
                "X max": 100.0,
                "Y min": 0.0,
                "Y max": 30.0,
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
                "X min": None,
                "X max": None,
                "Y min": 0.01,
                "Y max": 100.0,
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
    assert result["X min"].tolist()[0] == 0.0
    assert result["X max"].tolist()[0] == 20.0
    assert result["Y min"].tolist()[1] == 0.01
    assert result["Y max"].tolist()[1] == 100.0
    assert result["Панель"].tolist() == [1, 2]
    assert result["Порядок"].tolist() == [1, 2]


def test_duplicate_keeps_scientific_spec_and_range_independent_copy() -> None:
    from petrolab.ui.panel_manager import _panel_rows_after_actions

    source = _frame()
    source.loc[0, "Дублировать"] = True
    result, truncated = _panel_rows_after_actions(source)
    assert result is not None
    assert truncated is False
    assert len(result) == 4
    assert result.iloc[0]["X"] == result.iloc[1]["X"] == "Al2O3"
    assert result.iloc[0]["Y"] == result.iloc[1]["Y"] == "TiO2"
    assert result.iloc[0]["X min"] == result.iloc[1]["X min"] == 0.0
    assert result.iloc[0]["X max"] == result.iloc[1]["X max"] == 20.0
    assert result.iloc[1]["Название"] == "Ti–Al · копия"
    assert bool(result.iloc[1]["Дублировать"]) is False
    assert result["Порядок"].tolist() == [1, 2, 3, 4]

    result.loc[1, "Y"] = "FeOt"
    result.loc[1, "X max"] = 10.0
    assert result.loc[0, "Y"] == "TiO2"
    assert result.loc[1, "Y"] == "FeOt"
    assert result.loc[0, "X max"] == 20.0
    assert result.loc[1, "X max"] == 10.0


def test_range_validation_requires_complete_ordered_positive_log_pairs() -> None:
    from petrolab.ui.panel_manager import _panel_range_problems

    incomplete = pd.Series({"X min": 0.0, "X max": None, "Y min": None, "Y max": None, "log X": False, "log Y": False})
    assert any("обе границы" in item for item in _panel_range_problems(incomplete, 1))

    reversed_range = pd.Series({"X min": 10.0, "X max": 5.0, "Y min": None, "Y max": None, "log X": False, "log Y": False})
    assert any("X min должен быть меньше" in item for item in _panel_range_problems(reversed_range, 2))

    nonpositive_log = pd.Series({"X min": 0.0, "X max": 10.0, "Y min": None, "Y max": None, "log X": True, "log Y": False})
    assert any("log X" in item for item in _panel_range_problems(nonpositive_log, 3))

    valid = pd.Series({"X min": 0.1, "X max": 10.0, "Y min": 0.0, "Y max": 20.0, "log X": True, "log Y": False})
    assert _panel_range_problems(valid, 4) == []


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
    test_duplicate_keeps_scientific_spec_and_range_independent_copy()
    test_range_validation_requires_complete_ordered_positive_log_pairs()
    test_cannot_remove_every_panel()
    test_duplicate_respects_ten_panel_limit()
    print("v0.15.8 panel manager structure: OK")


if __name__ == "__main__":
    main()
