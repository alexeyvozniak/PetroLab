from __future__ import annotations


def _base_spec(**overrides):
    from petrolab.ui.plot_spec import PlotSpec

    payload = dict(
        dataset_ids=(7,),
        analysis_ids=("a1", "a2"),
        x="Al2O3",
        y="TiO2",
        group_column="Generation",
        style_map={"core": {"marker": "o"}, "rim": {"marker": "s"}},
    )
    payload.update(overrides)
    return PlotSpec(**payload)


def test_old_plot_spec_payload_remains_valid() -> None:
    from petrolab.ui.plot_spec import PlotSpec

    spec = PlotSpec.from_dict(
        {
            "dataset_ids": [7],
            "analysis_ids": ["a1"],
            "x": "MgO",
            "y": "FeOt",
            "group_column": "Generation",
            "style_map": {"core": {"marker": "o"}},
        }
    )
    assert spec.visible_series == ()
    assert spec.marker_size == 0.0
    assert spec.figure_preset == ""
    assert spec.show_grid is False


def test_normalization_completes_visible_series_and_quick_appearance() -> None:
    from petrolab.ui.plot_spec import normalize_plot_spec

    state: dict[str, object] = {"quick_marker_size": 74}
    normalized = normalize_plot_spec(
        _base_spec(),
        state,
        default_preset="Lithos",
        default_grid=True,
    )
    assert normalized.analysis_ids == ("a1", "a2")
    assert normalized.visible_series == ("core", "rim")
    assert normalized.marker_size == 74.0
    assert normalized.figure_preset == "Lithos"
    assert normalized.show_grid is True


def test_explicit_plot_spec_appearance_wins_over_runtime_defaults() -> None:
    from petrolab.ui.plot_spec import normalize_plot_spec

    normalized = normalize_plot_spec(
        _base_spec(
            visible_series=("rim",),
            marker_size=38,
            figure_preset="Custom journal",
            show_grid=False,
        ),
        {"quick_marker_size": 99},
        default_preset="Lithos",
        default_grid=True,
    )
    assert normalized.visible_series == ("rim",)
    assert normalized.marker_size == 38.0
    assert normalized.figure_preset == "Custom journal"
    assert normalized.show_grid is False


def test_send_to_multi_panel_seeds_appearance_without_changing_science() -> None:
    from petrolab.ui.plot_spec import (
        MULTI_PANEL_INBOX_KEY,
        MULTI_PANEL_VISIBLE_SERIES_KEY,
        peek_multi_panel_inbox,
        send_to_multi_panel,
    )

    state: dict[str, object] = {}
    spec = _base_spec(
        visible_series=("core",),
        marker_size=62,
        figure_preset="Lithos",
        show_grid=True,
    )
    send_to_multi_panel(spec, state)
    inbox = peek_multi_panel_inbox(state)
    assert inbox is not None
    assert inbox.dataset_ids == (7,)
    assert inbox.analysis_ids == ("a1", "a2")
    assert inbox.x == "Al2O3" and inbox.y == "TiO2"
    assert inbox.visible_series == ("core",)
    assert state["multi_panel_marker"] == 62
    assert state["multi_panel_preset"] == "Lithos"
    assert state["multi_panel_grid"] is True
    assert state[MULTI_PANEL_VISIBLE_SERIES_KEY] == ["core"]
    assert isinstance(state[MULTI_PANEL_INBOX_KEY], dict)


def main() -> None:
    test_old_plot_spec_payload_remains_valid()
    test_normalization_completes_visible_series_and_quick_appearance()
    test_explicit_plot_spec_appearance_wins_over_runtime_defaults()
    test_send_to_multi_panel_seeds_appearance_without_changing_science()
    print("v0.15.8 complete PlotSpec handoff: OK")


if __name__ == "__main__":
    main()
