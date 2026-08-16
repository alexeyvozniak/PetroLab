from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd


def test_measurement_sections_keep_scientific_roles_separate() -> None:
    from petrolab.ui.record_detail import record_measurement_columns

    frame = pd.DataFrame(
        {
            "Sample": ["A"],
            "SiO2": [40.0],
            "MgO": [20.0],
            "Nb [µg/g]": [15.0],
            "La ppm": [20.0],
            "Si_apfu": [2.8],
            "QC уровень": ["ok"],
            "_analysis_id": ["a1"],
        }
    )
    sections = record_measurement_columns(frame)
    assert {"SiO2", "MgO"}.issubset(sections["Микрозонд"])
    assert {"Nb [µg/g]", "La ppm"}.issubset(sections["Trace"])
    assert "Si_apfu" in sections["APFU"]
    assert "QC уровень" in sections["QC"]
    assert "_analysis_id" not in sum(sections.values(), [])


def test_identity_never_uses_internal_ids() -> None:
    from petrolab.ui.record_detail import record_identity

    row = pd.Series(
        {
            "Sample": "KIV-2",
            "Grain": "g3",
            "Point": "p17",
            "Generation": "core",
            "_analysis_id": "very-secret-uuid",
            "_dataset_id": 99,
        }
    )
    pairs = record_identity(row)
    text = " ".join(f"{key} {value}" for key, value in pairs)
    assert "KIV-2" in text and "g3" in text and "p17" in text
    assert "very-secret-uuid" not in text
    assert "_analysis_id" not in text
    assert "_dataset_id" not in text


def test_provenance_uses_human_dataset_metadata_not_dataset_id() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_record_") as tmp:
        os.environ["PETROLAB_DATA_DIR"] = str(Path(tmp) / "data")
        from petrolab.db import add_dataset, create_project, replace_dataset_rows
        from petrolab.ui.record_detail import record_provenance

        project_id = create_project("Record detail", "")
        dataset_id = add_dataset(
            project_id=project_id,
            name="Mica analyses",
            mineral_key="mica",
            source_filename="article.xlsx",
            source_sheet="Table 2",
            source_sha256="test",
            csv_path="",
            row_count=1,
            source_path="",
            source_kind="article",
            header_row=1,
            column_map={},
            sync_enabled=False,
        )
        replace_dataset_rows(dataset_id, pd.DataFrame({"Sample": ["A"], "SiO2": [40.0]}), source_rows=[17])
        row = pd.Series({"_dataset_id": dataset_id, "_source_row": 17, "Method": "EPMA"})
        pairs = record_provenance(row)
        text = " | ".join(f"{key}: {value}" for key, value in pairs)
        assert "Mica analyses" in text
        assert "article.xlsx" in text
        assert "Table 2" in text
        assert "17" in text
        assert "EPMA" in text
        assert "_dataset_id" not in text


def main() -> None:
    test_measurement_sections_keep_scientific_roles_separate()
    test_identity_never_uses_internal_ids()
    test_provenance_uses_human_dataset_metadata_not_dataset_id()
    print("v0.15.8 record detail: OK")


if __name__ == "__main__":
    main()
