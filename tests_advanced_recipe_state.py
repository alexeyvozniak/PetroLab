from petrolab.ui.advanced_recipe_state import (
    advanced_recipe_for_entry,
    clear_current_advanced_recipe,
    current_advanced_recipe,
    deep_state_summary,
    store_current_advanced_recipe,
)


def main() -> None:
    parked = {
        "dataset_ids": [4, 5],
        "analysis_ids": ["a", "b"],
        "minerals": ["mica"],
        "x": "Al2O3",
        "y": "TiO2",
        "group_col": "Generation",
        "column_filters": {"Generation": ["core"]},
        "outlier_filters": {"interactive_excluded_ids": ["b"]},
        "x_min": 10.0,
        "x_max": 18.0,
        "annotate": True,
        "label_col": "Sample",
        "journal_preset": "Lithos",
        "style_map": {"core": {"marker": "o"}},
    }
    compact = {
        "dataset_ids": [4, 5],
        "analysis_ids": ["a", "b"],
        "minerals": ["mica"],
        "query": "N-HF",
        "visible_sources": ["Paper A"],
        "hidden_sources": ["Paper B"],
        "x": "Al2O3",
        "y": "TiO2",
        "group_col": "Generation",
        "title": "Compact title",
        "log_x": False,
        "log_y": False,
        "marker_size": 52,
        "style_map": {"core": {"marker": "s"}},
    }

    resumed = advanced_recipe_for_entry(compact, parked)
    assert resumed.resumed_deep_state is True
    assert resumed.dropped_incompatible_deep_state is False
    assert resumed.recipe["column_filters"] == {"Generation": ["core"]}
    assert resumed.recipe["outlier_filters"]["interactive_excluded_ids"] == ["b"]
    assert resumed.recipe["x_min"] == 10.0
    assert resumed.recipe["title"] == "Compact title"
    assert resumed.recipe["style_map"]["core"]["marker"] == "s"
    assert "категориальные фильтры" in resumed.deep_summary
    assert "выбросы / исключённые точки" in resumed.deep_summary

    different_axes = dict(compact, x="FeO")
    dropped_axes = advanced_recipe_for_entry(different_axes, parked)
    assert dropped_axes.resumed_deep_state is False
    assert dropped_axes.dropped_incompatible_deep_state is True
    assert "column_filters" not in dropped_axes.recipe
    assert "outlier_filters" not in dropped_axes.recipe
    assert "x_min" not in dropped_axes.recipe
    assert dropped_axes.recipe["x"] == "FeO"

    different_datasets = dict(compact, dataset_ids=[4])
    dropped_dataset = advanced_recipe_for_entry(different_datasets, parked)
    assert dropped_dataset.dropped_incompatible_deep_state is True

    different_mineral = dict(compact, minerals=["apatite"])
    dropped_mineral = advanced_recipe_for_entry(different_mineral, parked)
    assert dropped_mineral.dropped_incompatible_deep_state is True

    state = {}
    store_current_advanced_recipe(state, parked)
    restored = current_advanced_recipe(state)
    assert restored == parked
    restored["x"] = "mutated outside"
    assert current_advanced_recipe(state)["x"] == "Al2O3"
    clear_current_advanced_recipe(state)
    assert current_advanced_recipe(state) == {}

    assert deep_state_summary({}) == ()
    print("Advanced recipe parked-state safety: OK")


if __name__ == "__main__":
    main()
