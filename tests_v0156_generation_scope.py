from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_generation_scope_", ignore_cleanup_errors=True) as tmp:
        os.environ["PETROLAB_DATA_DIR"] = str(Path(tmp) / "data")

        from petrolab.analysis_groups import set_work_group
        from petrolab.db import (
            add_dataset,
            create_project,
            get_or_create_library_project,
            link_dataset_to_project,
            load_dataset_dataframe,
            replace_dataset_rows,
        )
        from petrolab.generations import generation_map
        from petrolab.ui.pages.generations import (
            _project_analysis_ids,
            _project_work_group_map,
            _promote_project_work_group,
        )

        project_a = create_project("Project A")
        project_b = create_project("Project B")
        library = get_or_create_library_project()

        frame_a = pd.DataFrame([
            {"Sample": "A", "Point": "a1", "SiO2": 50.0},
            {"Sample": "A", "Point": "a2", "SiO2": 51.0},
        ])
        frame_b = pd.DataFrame([
            {"Sample": "B", "Point": "b1", "SiO2": 48.0},
            {"Sample": "B", "Point": "b2", "SiO2": 49.0},
        ])
        path_a = Path(tmp) / "a.csv"
        path_b = Path(tmp) / "b.csv"
        frame_a.to_csv(path_a, index=False)
        frame_b.to_csv(path_b, index=False)

        dataset_a = add_dataset(library, "Shared A", "generic", "a.xlsx", "Data", "sha-a", str(path_a), 2)
        dataset_b = add_dataset(library, "Shared B", "generic", "b.xlsx", "Data", "sha-b", str(path_b), 2)
        replace_dataset_rows(dataset_a, frame_a, source_rows=[2, 3])
        replace_dataset_rows(dataset_b, frame_b, source_rows=[2, 3])
        link_dataset_to_project(project_a, dataset_a, "A working", purpose="working")
        link_dataset_to_project(project_b, dataset_b, "B working", purpose="working")

        ids_a = load_dataset_dataframe(dataset_a, include_meta=True)["_analysis_id"].astype(str).tolist()
        ids_b = load_dataset_dataframe(dataset_b, include_meta=True)["_analysis_id"].astype(str).tolist()
        set_work_group(ids_a, "HF")
        set_work_group(ids_b, "HF")  # same visible name in another project

        allowed_a = _project_analysis_ids(project_a)
        assert allowed_a == set(ids_a), (allowed_a, ids_a)
        project_groups = _project_work_group_map(allowed_a)
        assert set(project_groups) == set(ids_a)
        assert set(project_groups.values()) == {"HF"}

        changed = _promote_project_work_group(allowed_a, "HF", "N-HF", rationale="scope test")
        assert changed == len(ids_a)
        mapping = generation_map()
        assert all(mapping.get(analysis_id) == "N-HF" for analysis_id in ids_a)
        assert all(analysis_id not in mapping for analysis_id in ids_b), mapping

    print("project-scoped Generation regression: OK")


if __name__ == "__main__":
    main()
