from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_export_membership_", ignore_cleanup_errors=True) as tmp:
        os.environ["PETROLAB_DATA_DIR"] = str(Path(tmp) / "data")

        from petrolab.db import (
            add_dataset,
            create_project,
            get_or_create_library_project,
            link_dataset_to_project,
            replace_dataset_rows,
        )
        from petrolab.ui.pages.export import _selected_membership_rows, _selected_project_ids

        working_project = create_project("Working project")
        library = get_or_create_library_project()
        frame = pd.DataFrame([{"Sample": "KIV-2", "SiO2": 48.5}])
        csv_path = Path(tmp) / "shared.csv"
        frame.to_csv(csv_path, index=False)
        dataset_id = add_dataset(
            library, "Shared chemistry", "generic", "shared.xlsx", "Data", "shared-sha",
            str(csv_path), len(frame),
        )
        replace_dataset_rows(dataset_id, frame, source_rows=[2])
        link_dataset_to_project(working_project, dataset_id, "working copy", purpose="working")

        project_ids = _selected_project_ids([dataset_id])
        assert working_project in project_ids, project_ids
        rows = _selected_membership_rows([dataset_id])
        assert any(
            int(row["project_id"]) == working_project
            and int(row["dataset_id"]) == dataset_id
            and row["purpose"] == "working"
            for row in rows
        ), rows

    print("export dataset-membership regression: OK")


if __name__ == "__main__":
    main()
