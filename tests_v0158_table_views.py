from __future__ import annotations

import os
import tempfile
from pathlib import Path


def test_state_roundtrip_and_selection_separation() -> None:
    from petrolab.ui.table_view_state import TableViewState, apply_table_view, capture_table_view

    prefix = "workspace_dataset_analyses"
    state: dict[str, object] = {
        f"{prefix}_query": "apatite",
        f"{prefix}_column_mode": "Свои",
        f"{prefix}_custom_fields": ["Sample", "CaO", "P2O5"],
        f"{prefix}_filter_column": "Generation",
        f"{prefix}_filter_values_Generation": ["core", "rim"],
        f"{prefix}_group_col": "Sample",
        f"{prefix}_sort_column": "CaO",
        f"{prefix}_sort_direction": "По убыванию",
        "petrolab_selection_context": {"analysis_ids": ["a1", "a2"]},
        "petrolab_hidden_analysis_ids": ["a3"],
        "petrolab_excluded_analysis_ids": ["a4"],
    }
    captured = capture_table_view(state, prefix)
    assert captured.query == "apatite"
    assert captured.custom_fields == ["Sample", "CaO", "P2O5"]
    assert captured.filter_values == ["core", "rim"]
    assert captured.group_column == "Sample"
    assert captured.sort_column == "CaO"

    payload = captured.to_dict()
    assert "analysis_ids" not in payload
    assert "selection" not in " ".join(payload).casefold()
    restored = TableViewState.from_dict(payload)

    target: dict[str, object] = {
        "petrolab_selection_context": {"analysis_ids": ["keep-me"]},
        "petrolab_hidden_analysis_ids": ["hidden-keep"],
        "petrolab_excluded_analysis_ids": ["excluded-keep"],
    }
    apply_table_view(target, prefix, restored)
    assert target[f"{prefix}_query"] == "apatite"
    assert target[f"{prefix}_filter_values_Generation"] == ["core", "rim"]
    assert target["petrolab_selection_context"] == {"analysis_ids": ["keep-me"]}
    assert target["petrolab_hidden_analysis_ids"] == ["hidden-keep"]
    assert target["petrolab_excluded_analysis_ids"] == ["excluded-keep"]


def test_numeric_filter_roundtrip() -> None:
    from petrolab.ui.table_view_state import apply_table_view, capture_table_view

    prefix = "table"
    source: dict[str, object] = {
        f"{prefix}_filter_column": "MgO",
        f"{prefix}_filter_min_MgO": 12.5,
        f"{prefix}_filter_max_MgO": 23.1,
    }
    captured = capture_table_view(source, prefix)
    assert captured.filter_min == 12.5
    assert captured.filter_max == 23.1
    target: dict[str, object] = {}
    apply_table_view(target, prefix, captured)
    assert target[f"{prefix}_filter_min_MgO"] == 12.5
    assert target[f"{prefix}_filter_max_MgO"] == 23.1


def test_persistent_store_is_project_and_scope_specific() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_views_") as tmp:
        os.environ["PETROLAB_DATA_DIR"] = str(Path(tmp) / "data")

        from petrolab.db import create_project
        from petrolab.table_views import delete_table_view, list_table_views, save_table_view

        project_a = create_project("Views A", "")
        project_b = create_project("Views B", "")

        first_id = save_table_view(project_a, "dataset:10", "Для статьи", {"query": "apatite"})
        assert first_id > 0
        save_table_view(project_a, "dataset:10", "Для статьи", {"query": "mica"})
        save_table_view(project_a, "dataset:11", "Для статьи", {"query": "other"})
        save_table_view(project_b, "dataset:10", "Для статьи", {"query": "foreign"})

        views = list_table_views(project_a, "dataset:10")
        assert len(views) == 1
        assert views[0]["name"] == "Для статьи"
        assert views[0]["config"]["query"] == "mica"
        assert len(list_table_views(project_a, "dataset:11")) == 1
        assert len(list_table_views(project_b, "dataset:10")) == 1

        assert delete_table_view(project_a, "dataset:10", "Для статьи") is True
        assert list_table_views(project_a, "dataset:10") == []
        assert len(list_table_views(project_b, "dataset:10")) == 1


def main() -> None:
    test_state_roundtrip_and_selection_separation()
    test_numeric_filter_roundtrip()
    test_persistent_store_is_project_and_scope_specific()
    print("v0.15.8 saved table views: OK")


if __name__ == "__main__":
    main()
