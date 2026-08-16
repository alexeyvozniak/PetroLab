from __future__ import annotations

import os
import tempfile
from io import BytesIO
from pathlib import Path

import pandas as pd


def test_public_export_hides_internal_columns_and_adds_human_point() -> None:
    from petrolab.ui.selection_export import public_selection_frame

    frame = pd.DataFrame(
        {
            "_analysis_id": ["secret-a", "secret-b"],
            "_dataset_id": [7, 7],
            "Sample": ["KIV-2", "KIV-2"],
            "Grain": ["g3", "g3"],
            "Point": ["p17", "p18"],
            "Generation": ["core", "rim"],
            "SiO2": [40.0, 41.0],
        }
    )
    public = public_selection_frame(frame)
    assert "Точка" in public.columns
    assert public["Точка"].str.contains("KIV-2").all()
    assert not any(str(column).startswith("_") for column in public.columns)
    text = public.to_csv(index=False)
    assert "secret-a" not in text and "secret-b" not in text


def test_project_resolution_ignores_current_filtered_view() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_export_") as tmp:
        os.environ["PETROLAB_DATA_DIR"] = str(Path(tmp) / "data")
        from petrolab.db import add_dataset, create_project, replace_dataset_rows
        from petrolab.ui.selection_export import resolve_selection_dataframe

        project_id = create_project("Selection export", "")
        dataset_id = add_dataset(
            project_id=project_id,
            name="Full dataset",
            mineral_key="mica",
            source_filename="full.xlsx",
            source_sheet="Mica",
            source_sha256="test",
            csv_path="",
            row_count=3,
            source_path="",
            source_kind="upload",
            header_row=1,
            column_map={},
            sync_enabled=False,
        )
        source = pd.DataFrame({
            "Sample": ["A", "B", "C"],
            "Point": ["p1", "p2", "p3"],
            "SiO2": [40.0, 41.0, 42.0],
        })
        replace_dataset_rows(dataset_id, source, source_rows=[2, 3, 4])

        from petrolab.derived import load_unified_with_derived
        full = load_unified_with_derived(project_id, [dataset_id])
        ids = full["_analysis_id"].astype(str).tolist()
        filtered_current = full.iloc[[0]].copy()
        resolved = resolve_selection_dataframe(
            project_id,
            [ids[2], ids[0]],
            current_dataframe=filtered_current,
        )
        assert resolved["_analysis_id"].astype(str).tolist() == [ids[2], ids[0]]
        assert resolved["Sample"].tolist() == ["C", "A"]


def test_xlsx_contains_only_public_selection_fields() -> None:
    from petrolab.ui.selection_export import selection_xlsx_bytes

    frame = pd.DataFrame({
        "_analysis_id": ["secret"],
        "Sample": ["A"],
        "Point": ["p1"],
        "SiO2": [40.0],
    })
    payload = selection_xlsx_bytes(frame)
    restored = pd.read_excel(BytesIO(payload), sheet_name="Selection")
    assert "Точка" in restored.columns
    assert "_analysis_id" not in restored.columns
    assert "secret" not in restored.to_csv(index=False)


def main() -> None:
    test_public_export_hides_internal_columns_and_adds_human_point()
    test_project_resolution_ignores_current_filtered_view()
    test_xlsx_contains_only_public_selection_fields()
    print("v0.15.8 exact Selection export: OK")


if __name__ == "__main__":
    main()
