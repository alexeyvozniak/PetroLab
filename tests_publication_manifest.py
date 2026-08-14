from __future__ import annotations

import os
import tempfile
from io import BytesIO
from pathlib import Path

import pandas as pd
from openpyxl import load_workbook


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_manifest_", ignore_cleanup_errors=True) as tmp:
        os.environ["PETROLAB_DATA_DIR"] = str(Path(tmp) / "data")
        from petrolab.db import add_dataset, create_project, replace_dataset_rows
        from petrolab.publication_manifest import build_selection_manifest, workbook_with_manifest

        project_id = create_project("Manifest test")
        dataset_id = add_dataset(project_id, "Mica", "mica", "mica.xlsx", "Data", "sha", "", 1)
        replace_dataset_rows(dataset_id, pd.DataFrame([{"Sample": "PG-1", "SiO2": 40.0}]))
        from petrolab.db import load_dataset_dataframe

        dataframe = load_dataset_dataframe(dataset_id, include_meta=True)
        manifest = build_selection_manifest(
            kind="xy_figure",
            dataframe=dataframe,
            dataset_ids=[dataset_id],
            filters={"Sample": ["PG-1"]},
            recipe={"x": "SiO2", "y": "TiO2"},
        )
        assert manifest["analysis_ids"] == dataframe["_analysis_id"].astype(str).tolist()
        assert manifest["dataset_ids"] == [dataset_id]
        workbook = workbook_with_manifest({"Points": dataframe}, manifest)
        book = load_workbook(filename=BytesIO(workbook), read_only=True)
        assert {"Points", "Manifest"}.issubset(book.sheetnames)
        assert "petrolab-publication-manifest/v1" in str(book["Manifest"]["A2"].value)

    print("publication manifest tests: OK")


if __name__ == "__main__":
    main()
