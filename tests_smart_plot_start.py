from petrolab.ui.plot_spec import CURRENT_PLOT_SPEC_KEY, PlotSpec
from petrolab.ui.smart_plot_start import (
    QUICK_CUSTOM_GRAPH_CHOICE,
    advanced_recipe_from_spec,
    choose_xy_recommendation,
    clear_exact_plot_scope,
    consume_plot_scope,
    resolve_plot_scope,
    restore_quick_plot_state,
    seed_import_plot_handoff,
    seed_plot_handoff,
    seed_selection_plot_handoff,
    seed_xy_state,
    sync_xy_recommendation_state,
    xy_recommendations,
)


def test_explicit_route_scope_wins_over_work_context_without_mixing_it():
    scope = resolve_plot_scope(
        available_dataset_ids=[1, 2, 3],
        work_context={"dataset_ids": [1, 2], "analysis_ids": ["ctx-a"], "label": "Sample PG-15"},
        requested_dataset_ids=[3, 999],
        requested_analysis_ids=["route-a", "route-a", "route-b"],
        requested_context={"origin": "database", "label": "Search · apatite"},
    )
    assert scope.dataset_ids == (3,)
    assert scope.analysis_ids == ("route-a", "route-b")
    assert scope.context["origin"] == "database"
    assert scope.context_label == "Search · apatite"
    assert scope.explicit is True


def test_dataset_only_route_does_not_inherit_stale_work_context_points():
    scope = resolve_plot_scope(
        available_dataset_ids=[1, 2, 3],
        work_context={"dataset_ids": [1], "analysis_ids": ["old-a"], "label": "Old sample"},
        requested_dataset_ids=[3],
        requested_analysis_ids=[],
        requested_context={"origin": "import"},
    )
    assert scope.dataset_ids == (3,)
    assert scope.analysis_ids == ()
    assert scope.context == {"origin": "import"}


def test_work_context_is_used_when_route_handoff_is_absent():
    scope = resolve_plot_scope(
        available_dataset_ids=[1, 2, 3],
        work_context={"dataset_ids": [2], "analysis_ids": ["a", "b"], "label": "Kandalaksha"},
    )
    assert scope.dataset_ids == (2,)
    assert scope.analysis_ids == ("a", "b")
    assert scope.context_label == "Kandalaksha"
    assert scope.explicit is False


def test_all_accessible_datasets_are_fallback_only_when_no_context_exists():
    scope = resolve_plot_scope(available_dataset_ids=[3, 1, 3, 2])
    assert scope.dataset_ids == (3, 1, 2)
    assert scope.analysis_ids == ()


def test_exact_selection_scope_survives_streamlit_reruns_until_explicitly_broadened():
    state = {}
    seed_selection_plot_handoff(
        state,
        dataset_ids=[10, 11],
        analysis_ids=["a2", "a4"],
        origin="PCA",
    )
    first = consume_plot_scope(
        state,
        project_id=5,
        available_dataset_ids=[10, 11, 12],
        work_context={"dataset_ids": [12], "analysis_ids": ["wrong"], "label": "Old context"},
    )
    assert first.dataset_ids == (10, 11)
    assert first.analysis_ids == ("a2", "a4")
    assert first.context_label == "Selection · 2 точек"

    second = consume_plot_scope(
        state,
        project_id=5,
        available_dataset_ids=[10, 11, 12],
        work_context={"dataset_ids": [12], "analysis_ids": ["wrong"], "label": "Old context"},
    )
    assert second.dataset_ids == (10, 11)
    assert second.analysis_ids == ("a2", "a4")
    assert second.explicit is True

    clear_exact_plot_scope(state)
    broadened = consume_plot_scope(
        state,
        project_id=5,
        available_dataset_ids=[10, 11, 12],
        work_context={"dataset_ids": [12], "analysis_ids": ["wrong"], "label": "Old context"},
    )
    assert broadened.dataset_ids == (10, 11)
    assert broadened.analysis_ids == ()


def test_project_change_drops_persisted_plot_scope_instead_of_leaking_ids():
    state = {}
    seed_selection_plot_handoff(state, dataset_ids=[10], analysis_ids=["a2"])
    first = consume_plot_scope(state, project_id=1, available_dataset_ids=[10])
    assert first.analysis_ids == ("a2",)

    second = consume_plot_scope(
        state,
        project_id=2,
        available_dataset_ids=[20],
        work_context={"dataset_ids": [20], "analysis_ids": ["b1"], "label": "Project 2"},
    )
    assert second.dataset_ids == (20,)
    assert second.analysis_ids == ("b1",)
    assert second.context_label == "Project 2"


def test_canonical_handoff_preserves_provenance_and_resets_stale_graph_state():
    state = {
        "_plots_show_advanced": True,
        "loaded_recipe": {"x": "old-x", "y": "old-y"},
        CURRENT_PLOT_SPEC_KEY: {"dataset_ids": [1], "analysis_ids": [], "x": "old-x", "y": "old-y"},
        "_quick_resume_style_map": {"old": {"marker": "o"}},
        "_quick_graph_recommendation_signature": (("old", "x", "y", "note"),),
        "workflow_plot_notice": "old notice",
        "unrelated": 1,
    }
    datasets, analyses = seed_plot_handoff(
        state,
        dataset_ids=[2, "3", 2],
        analysis_ids=["a", "b", "a"],
        context={"origin": "search", "query": "apatite", "label": "Поиск · apatite"},
        notice="Новый точный поиск.",
    )
    assert datasets == (2, 3)
    assert analyses == ("a", "b")
    assert state["workflow_plot_dataset_ids"] == [2, 3]
    assert state["workflow_plot_analysis_ids"] == ["a", "b"]
    assert state["workflow_plot_context"]["query"] == "apatite"
    assert state["workflow_plot_context"]["dataset_ids"] == [2, 3]
    assert state["workflow_plot_context"]["analysis_ids"] == ["a", "b"]
    assert state["workflow_plot_notice"] == "Новый точный поиск."
    assert "_plots_show_advanced" not in state
    assert "loaded_recipe" not in state
    assert CURRENT_PLOT_SPEC_KEY not in state
    assert "_quick_resume_style_map" not in state
    assert "_quick_graph_recommendation_signature" not in state
    assert state["unrelated"] == 1


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


def test_recommendation_universe_change_updates_owned_axes_but_not_custom_axes():
    mica = xy_recommendations(
        ["mica"],
        ["Al2O3", "TiO2", "FeO", "SiO2"],
        ["Al2O3", "TiO2", "FeO", "SiO2"],
    )
    state = {"quick_graph_choice": "rec:0", "quick_x": "Al2O3", "quick_y": "TiO2"}
    sync_xy_recommendation_state(state, mica)
    assert (state["quick_x"], state["quick_y"]) == ("Al2O3", "TiO2")

    mixed = xy_recommendations(
        ["mica", "apatite"],
        ["SiO2", "TiO2", "Al2O3"],
        ["SiO2", "TiO2", "Al2O3"],
    )
    sync_xy_recommendation_state(state, mixed)
    assert state["quick_graph_choice"] == "rec:0"
    assert (state["quick_x"], state["quick_y"]) == ("SiO2", "TiO2")

    custom = {
        "quick_graph_choice": QUICK_CUSTOM_GRAPH_CHOICE,
        "quick_x": "FeO",
        "quick_y": "MgO",
    }
    sync_xy_recommendation_state(custom, mica)
    assert custom["quick_graph_choice"] == QUICK_CUSTOM_GRAPH_CHOICE
    assert (custom["quick_x"], custom["quick_y"]) == ("FeO", "MgO")


def test_advanced_to_compact_restore_keeps_representable_plotspec_state_only():
    state = {"_quick_series_epoch": 4}
    spec = PlotSpec(
        dataset_ids=(4, 5),
        analysis_ids=("a", "b"),
        x="FeO",
        y="TiO2",
        group_column="Generation",
        title="Advanced mica view",
        log_x=True,
        log_y=False,
        visible_sources=("Paper A",),
        hidden_sources=("Paper B",),
        visible_series=("core",),
        style_map={"core": {"marker": "s", "alpha": 0.7}},
        marker_size=52,
    )
    restore_quick_plot_state(state, spec)
    assert state["quick_x"] == "FeO"
    assert state["quick_y"] == "TiO2"
    assert state["quick_graph_choice"] == QUICK_CUSTOM_GRAPH_CHOICE
    assert state["quick_log_x"] is True
    assert state["quick_log_y"] is False
    assert state["quick_title"] == "Advanced mica view"
    assert state["quick_marker_size"] == 52
    assert state["_quick_resume_group_pending"] == "Generation"
    assert state["_quick_resume_visible_series"] == ["core"]
    assert state["_quick_resume_style_map"]["core"]["marker"] == "s"
    assert state["quick_plot_visibility_filters"] == {"source": ["Paper A"]}
    assert state["quick_plot_visibility_values_source"] == ["Paper A"]
    assert state["_quick_series_epoch"] == 5
    # Membership is deliberately not replaced here: DataUniverse and Selection
    # belong to their own canonical contexts, not to the compact-view restore.
    assert "workflow_plot_analysis_ids" not in state


def test_post_import_handoff_targets_normal_plot_and_clears_deep_panel_state():
    state = {
        "multi_panel_layout": "2x2",
        "_multi_panel_incoming_visible_series": ["old"],
        "_plots_show_advanced": True,
        "loaded_recipe": {"x": "old"},
        "keep_me": 1,
    }
    datasets = seed_import_plot_handoff(state, [7, "8", 7, "bad"])
    assert datasets == (7, 8)
    assert state["workflow_plot_dataset_ids"] == [7, 8]
    assert state["workflow_plot_analysis_ids"] == []
    assert state["workflow_plot_context"]["origin"] == "import"
    assert "безопасный стартовый график" in state["workflow_plot_notice"]
    assert "multi_panel_layout" not in state
    assert "_multi_panel_incoming_visible_series" not in state
    assert "_plots_show_advanced" not in state
    assert "loaded_recipe" not in state
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
