from __future__ import annotations

import pandas as pd


def test_advanced_editor_builds_same_portable_plot_spec() -> None:
    from petrolab.ui.advanced_plot_handoff import advanced_plot_spec

    frame = pd.DataFrame(
        {
            "_analysis_id": ["a1", "a2"],
            "Al2O3": [12.0, 13.0],
            "TiO2": [2.0, 3.0],
            "Generation": ["core", "rim"],
        }
    )
    styles = {"core": {"marker": "o"}, "rim": {"marker": "s"}}
    appearance = {
        "x_label": "Al₂O₃, wt.%",
        "y_label": "TiO₂, wt.%",
        "title": "Mica evolution",
        "log_x": False,
        "log_y": True,
        "marker_size": 58,
        "show_grid": True,
    }
    spec = advanced_plot_spec(
        frame,
        dataset_ids=[7, 8],
        x="Al2O3",
        y="TiO2",
        group_column="Generation",
        visible_sources=["Article A"],
        hidden_sources=["Article B"],
        journal_preset="Advanced journal",
        appearance=appearance,
        styles=styles,
    )
    assert spec.dataset_ids == (7, 8)
    assert spec.analysis_ids == ("a1", "a2")
    assert spec.x == "Al2O3" and spec.y == "TiO2"
    assert spec.group_column == "Generation"
    assert spec.x_label == "Al₂O₃, wt.%"
    assert spec.y_label == "TiO₂, wt.%"
    assert spec.title == "Mica evolution"
    assert spec.log_y is True
    assert spec.visible_sources == ("Article A",)
    assert spec.hidden_sources == ("Article B",)
    assert spec.visible_series == ("core", "rim")
    assert spec.style_map == styles
    assert spec.marker_size == 58.0
    assert spec.figure_preset == "Advanced journal"
    assert spec.show_grid is True


def test_advanced_handoff_uses_only_rows_that_reached_graph() -> None:
    from petrolab.ui.advanced_plot_handoff import advanced_plot_spec

    # Simulates the post-filter/outlier dataframe: a2 is absent and must not be
    # reintroduced merely because its dataset remains selected.
    frame = pd.DataFrame({"_analysis_id": ["a1", "a3"], "X": [1.0, 3.0], "Y": [2.0, 4.0]})
    spec = advanced_plot_spec(
        frame,
        dataset_ids=[5],
        x="X",
        y="Y",
        group_column=None,
        visible_sources=[],
        hidden_sources=[],
        journal_preset="Свой",
        appearance={"marker_size": 40},
        styles={},
    )
    assert spec.analysis_ids == ("a1", "a3")
    assert spec.visible_series == ()
    assert spec.x_label == "X" and spec.y_label == "Y"


def main() -> None:
    test_advanced_editor_builds_same_portable_plot_spec()
    test_advanced_handoff_uses_only_rows_that_reached_graph()
    print("v0.15.8 advanced XY PlotSpec handoff: OK")


if __name__ == "__main__":
    main()
