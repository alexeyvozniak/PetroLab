from petrolab.ui.plot_spec import PlotSpec
from petrolab.ui.smart_plot_start import (
    advanced_recipe_from_spec,
    choose_xy_recommendation,
    resolve_plot_scope,
    seed_import_plot_handoff,
    seed_selection_plot_handoff,
    seed_xy_state,
)


def test_explicit_route_scope_wins_over_work_context():
    scope = resolve_plot_scope(
        available_dataset_ids=[1, 2, 3],
        work_context={"dataset_ids": [1, 2], "analysis_ids": ["ctx-a"], "label": "Sample PG-15"},
        requested_dataset_ids=[3, 999],
        requested_analysis_ids=["route-a", "route-a", "route-b"],
        requested_context={"origin": "database"},
    )
    assert scope.dataset_ids == (3,)
    assert scope.analysis_ids == ("route-a", "route-b")
    assert scope.context == {"origin": "database"}
    assert scope.context_label == "Sample PG-15"


def test_work_context_is_used_when_route_handoff_is_absent():
    scope = resolve_plot_scope(
        available_dataset_ids=[1, 2, 3],
        work_context={"dataset_ids": [2], "analysis_ids": ["a", "b"], "label": "Kandalaksha"},
    )
    assert scope.dataset_ids == (2,)
    assert scope.analysis_ids == ("a", "b")
    assert scope.context_label == "Kandalaksha"


def test_all_accessible_datasets_are_fallback_only_when_no_context_exists():
    scope = resolve_plot_scope(available_dataset_ids=[3, 1, 3, 2])
    assert scope.dataset_ids == (3, 1, 2)
    assert scope.analysis_ids == ()


def test_mica_smart_start_uses_first_available_scientific_pair():
    rec = choose_xy_recommendation(
        ["mica"],
        ["Sample", "Al2O3", "TiO2", "FeO"],
        ["Al2O3", "TiO2", "FeO"],
    )
    assert rec is not None
    assert (rec.x, rec.y) == ("Al2O3", "TiO2")


def test_mixed_mineral_scope_falls_back_to_neutral_numeric_pair():
    rec = choose_xy_recommendation(
        ["mica", "apatite"],
        ["SiO2", "TiO2", "Al2O3"],
        ["SiO2", "TiO2", "Al2O3"],
    )
    assert rec is not None
    assert (rec.x, rec.y) == ("SiO2", "TiO2")


def test_seed_xy_state_preserves_valid_manual_axes():
    state = {"quick_x": "FeO", "quick_y": "MgO"}
    rec = choose_xy_recommendation(
        ["mica"],
        ["Al2O3", "TiO2", "FeO", "MgO"],
        ["Al2O3", "TiO2", "FeO", "MgO"],
    )
    x, y = seed_xy_state(
        state,
        numeric_columns=["Al2O3", "TiO2", "FeO", "MgO"],
        recommendation=rec,
    )
    assert (x, y) == ("FeO", "MgO")


def test_seed_xy_state_repairs_invalid_axes_with_recommendation():
    state = {"quick_x": "missing", "quick_y": "missing"}
    rec = choose_xy_recommendation(
        ["mica"],
        ["Al2O3", "TiO2", "FeO"],
        ["Al2O3", "TiO2", "FeO"],
    )
    x, y = seed_xy_state(
        state,
        numeric_columns=["Al2O3", "TiO2", "FeO"],
        recommendation=rec,
    )
    assert (x, y) == ("Al2O3", "TiO2")
    assert state["quick_x"] == "Al2O3"
    assert state["quick_y"] == "TiO2"


def test_post_import_handoff_targets_normal_plot_and_clears_deep_panel_state():
    state = {
        "multi_panel_layout": "2x2",
        "_multi_panel_incoming_visible_series": ["old"],
        "keep_me": 1,
    }
    datasets = seed_import_plot_handoff(state, [7, "8", 7, "bad"])
    assert datasets == (7, 8)
    assert state["workflow_plot_dataset_ids"] == [7, 8]
    assert "безопасный стартовый график" in state["workflow_plot_notice"]
    assert "multi_panel_layout" not in state
    assert "_multi_panel_incoming_visible_series" not in state
    assert state["keep_me"] == 1


def test_selection_handoff_never_broadens_exact_analysis_ids_to_dataset_scope():
    state = {}
    datasets, analyses = seed_selection_plot_handoff(
        state,
        dataset_ids=[10, 11, 10],
        analysis_ids=["a2", "a4", "a2"],
        origin="PCA",
    )
    assert datasets == (10, 11)
    assert analyses == ("a2", "a4")
    assert state["workflow_plot_dataset_ids"] == [10, 11]
    assert state["workflow_plot_analysis_ids"] == ["a2", "a4"]
    assert state["workflow_plot_context"]["origin"] == "PCA"
    assert state["workflow_plot_context"]["analysis_ids"] == ["a2", "a4"]


def test_advanced_recipe_is_adapter_from_plotspec_not_new_truth():
    spec = PlotSpec(
        dataset_ids=(4, 5),
        analysis_ids=("a", "b"),
        x="Al2O3",
        y="TiO2",
        group_column="Generation",
        x_label="Al₂O₃",
        y_label="TiO₂",
        title="Mica evolution",
        log_x=False,
        log_y=True,
        visible_sources=("Paper A",),
        hidden_sources=("Paper B",),
        style_map={"core": {"marker": "o"}},
        marker_size=44,
    )
    recipe = advanced_recipe_from_spec(spec, minerals=["mica", "mica"], query="N-HF")
    assert recipe["dataset_ids"] == [4, 5]
    assert recipe["minerals"] == ["mica"]
    assert recipe["x"] == "Al2O3"
    assert recipe["y"] == "TiO2"
    assert recipe["group_col"] == "Generation"
    assert recipe["visible_sources"] == ["Paper A"]
    assert recipe["hidden_sources"] == ["Paper B"]
    assert recipe["query"] == "N-HF"
