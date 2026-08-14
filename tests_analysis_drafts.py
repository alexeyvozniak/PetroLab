from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

import petrolab.analysis_drafts as drafts


def _change(analysis_id: str, column: str, old, new, dataset_id: int = 1):
    return {
        "analysis_id": analysis_id,
        "dataset_id": dataset_id,
        "source_row": 2,
        "column_name": column,
        "old_value": old,
        "new_value": new,
    }


with tempfile.TemporaryDirectory() as temp_dir:
    drafts.DRAFT_DB_PATH = Path(temp_dir) / "drafts.sqlite3"

    original = pd.DataFrame([
        {"_analysis_id": "a1", "_dataset_id": 1, "SiO2": 40.0, "Generation": "core"},
        {"_analysis_id": "a2", "_dataset_id": 1, "SiO2": 41.0, "Generation": "rim"},
    ])

    state = drafts.replace_visible_analysis_draft(
        7,
        ["a1"],
        ["SiO2", "Generation"],
        [_change("a1", "SiO2", 40.0, 40.5), _change("a1", "Generation", "core", "core-1")],
    )
    assert len(state.changes) == 2
    assert drafts.DRAFT_DB_PATH.exists()

    restored = drafts.apply_analysis_draft(original, state.changes)
    row = restored.dataframe.loc[restored.dataframe["_analysis_id"] == "a1"].iloc[0]
    assert float(row["SiO2"]) == 40.5
    assert row["Generation"] == "core-1"
    assert len(restored.applied) == 2
    assert not restored.conflicts

    changed_source = original.copy()
    changed_source.loc[changed_source["_analysis_id"] == "a1", "SiO2"] = 39.9
    conflict = drafts.apply_analysis_draft(changed_source, state.changes)
    assert float(conflict.dataframe.loc[conflict.dataframe["_analysis_id"] == "a1", "SiO2"].iloc[0]) == 39.9
    assert len(conflict.conflicts) == 1

    updated = drafts.replace_visible_analysis_draft(
        7,
        ["a1"],
        ["SiO2"],
        [_change("a1", "SiO2", 40.0, 40.7)],
    )
    by_column = {item["column_name"]: item for item in updated.changes}
    assert by_column["SiO2"]["new_value"] == 40.7
    assert by_column["Generation"]["new_value"] == "core-1"

    remaining = drafts.remove_analysis_draft_changes(7, [_change("a1", "SiO2", 40.0, 40.7)])
    assert len(remaining.changes) == 1
    assert remaining.changes[0]["column_name"] == "Generation"

    drafts.clear_analysis_draft(7)
    assert not drafts.load_analysis_draft(7).changes

print("analysis draft tests: OK")
