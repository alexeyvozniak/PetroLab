from __future__ import annotations

import os
import tempfile
from pathlib import Path


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_global_context_", ignore_cleanup_errors=True) as tmp:
        os.environ["PETROLAB_DATA_DIR"] = str(Path(tmp) / "data")
        from petrolab.db import (
            add_dataset,
            create_project,
            get_or_create_library_project,
            link_dataset_to_project,
            list_accessible_datasets,
            list_projects,
        )

        article = create_project("Por'ya Guba micas")
        comparison = create_project("Turiy Mys micas")
        global_base = get_or_create_library_project()
        dataset_id = add_dataset(
            global_base, "Shared phlogopites", "mica", "micas.xlsx", "Data", "sha", "", 3,
        )
        link_dataset_to_project(article, dataset_id, "основной материал", purpose="working")
        link_dataset_to_project(comparison, dataset_id, "сравнение", purpose="comparison")

        assert {row["name"] for row in list_projects()} == {"Por'ya Guba micas", "Turiy Mys micas"}
        first = list_accessible_datasets(article)
        second = list_accessible_datasets(comparison)
        assert [int(row["id"]) for row in first] == [dataset_id]
        assert [int(row["id"]) for row in second] == [dataset_id]
        assert first[0]["membership_purpose"] == "working"
        assert second[0]["membership_purpose"] == "comparison"

    print("global project context tests: OK")


if __name__ == "__main__":
    main()
