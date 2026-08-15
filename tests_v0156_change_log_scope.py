from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd


def _make_dataset(project_id: int, tmp: str, name: str, sample: str) -> tuple[int, str]:
    from petrolab.db import add_dataset, load_dataset_dataframe, replace_dataset_rows

    frame = pd.DataFrame([{"Sample": sample, "Point": "p1", "SiO2": 50.0}])
    path = Path(tmp) / f"{name}.csv"
    frame.to_csv(path, index=False)
    dataset_id = add_dataset(
        project_id, name, "generic", f"{name}.xlsx", "Data", f"sha-{name}", str(path), 1,
    )
    replace_dataset_rows(dataset_id, frame, source_rows=[2])
    analysis_id = str(load_dataset_dataframe(dataset_id, include_meta=True).iloc[0]["_analysis_id"])
    return dataset_id, analysis_id


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_change_scope_", ignore_cleanup_errors=True) as tmp:
        os.environ["PETROLAB_DATA_DIR"] = str(Path(tmp) / "data")

        from petrolab.db import create_project, update_analysis_values
        from petrolab.ui.pages.change_log import _project_change_log

        project_a = create_project("A")
        project_b = create_project("B")
        dataset_a, analysis_a = _make_dataset(project_a, tmp, "a", "A")
        dataset_b, analysis_b = _make_dataset(project_b, tmp, "b", "B")

        update_analysis_values([
            {
                "dataset_id": dataset_a,
                "analysis_id": analysis_a,
                "column_name": "SiO2",
                "old_value": 50.0,
                "new_value": 50.5,
            }
        ])
        update_analysis_values([
            {
                "dataset_id": dataset_b,
                "analysis_id": analysis_b,
                "column_name": "SiO2",
                "old_value": 50.0,
                "new_value": 49.5,
            }
        ])

        rows_a = _project_change_log(project_a)
        rows_b = _project_change_log(project_b)
        assert rows_a and all(int(row["dataset_id"]) == dataset_a for row in rows_a), rows_a
        assert rows_b and all(int(row["dataset_id"]) == dataset_b for row in rows_b), rows_b
        assert all(str(row["analysis_id"]) != analysis_b for row in rows_a)
        assert all(str(row["analysis_id"]) != analysis_a for row in rows_b)

    print("cross-project change-history regression: OK")


if __name__ == "__main__":
    main()
