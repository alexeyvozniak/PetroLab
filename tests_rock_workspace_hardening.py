from __future__ import annotations

import gc
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


def _expect_value_error(callable_obj, text: str) -> None:
    try:
        callable_obj()
    except ValueError as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError(f"Expected ValueError containing: {text}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_rock_hardening_", ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        os.environ["PETROLAB_DATA_DIR"] = str(root / "data")

        from petrolab.db import (
            add_dataset,
            create_project,
            get_or_create_library_project,
            link_dataset_to_project,
            unlink_dataset_from_project,
        )
        from petrolab.repositories.rock_repository import create_rock, get_composition, set_mineral_links
        from petrolab.rock_workspace_model import rock_workspace_snapshot
        from petrolab.services.rock_service import import_rocks_wide
        from petrolab.storage import ensure_storage

        ensure_storage()
        project_id = create_project("Rock hardening", "")
        library_id = get_or_create_library_project()

        csv_path = root / "library_mica.csv"
        csv_path.write_text("Sample,Point,SiO2\nR1,P1,39.0\n", encoding="utf-8")
        dataset_id = add_dataset(
            library_id,
            "R1 mica from library",
            "phlogopite",
            "mica.xlsx",
            "Sheet1",
            "library-sha",
            str(csv_path),
            1,
            source_kind="managed_copy",
        )
        link_dataset_to_project(project_id, dataset_id, note="working context")

        rock_id = create_rock(project_id, "R1", lithology="lamprophyre")
        set_mineral_links(rock_id, [dataset_id])
        snapshot = rock_workspace_snapshot(project_id, rock_id)
        assert [int(item["id"]) for item in snapshot.linked_datasets] == [dataset_id]
        assert not any("больше не подключены" in warning for warning in snapshot.warnings)

        unlink_dataset_from_project(project_id, dataset_id)
        orphaned = rock_workspace_snapshot(project_id, rock_id)
        assert orphaned.linked_datasets == ()
        assert any(str(dataset_id) in warning and "больше не подключены" in warning for warning in orphaned.warnings)
        _expect_value_error(
            lambda: set_mineral_links(rock_id, [dataset_id]),
            "не подключён к текущему проекту",
        )

        # Partial update must replace provenance only for analytes actually updated.
        import_rocks_wide(
            pd.DataFrame({"Rock": ["R1"], "SiO2": [45.0], "MgO": [12.0]}),
            project_id=project_id,
            name_column="Rock",
            chemistry_method="XRF",
            source="major.xlsx",
            on_conflict="update",
        )
        import_rocks_wide(
            pd.DataFrame({"Rock": ["R1"], "La ppm": [100.0], "Ce ppm": [200.0]}),
            project_id=project_id,
            name_column="Rock",
            chemistry_method="LA-ICP-MS",
            source="trace.xlsx",
            on_conflict="update",
        )
        composition = get_composition(rock_id).set_index("analyte")
        assert float(composition.loc["SiO2", "value"]) == 45.0
        assert composition.loc["SiO2", "method"] == "XRF"
        assert composition.loc["SiO2", "source"] == "major.xlsx"
        assert composition.loc["MgO", "method"] == "XRF"
        assert composition.loc["La [µg/g]", "method"] == "LA-ICP-MS"
        assert composition.loc["La [µg/g]", "source"] == "trace.xlsx"
        assert np.isclose(float(composition.loc["La [µg/g]", "value"]), 100.0)

        _expect_value_error(
            lambda: import_rocks_wide(
                pd.DataFrame({"Rock": ["R1"], "SiO2": [np.inf]}),
                project_id=project_id,
                name_column="Rock",
                chemistry_method="XRF",
                source="bad.xlsx",
                on_conflict="update",
            ),
            "бесконечное/некорректное",
        )
        after_failure = get_composition(rock_id).set_index("analyte")
        assert float(after_failure.loc["SiO2", "value"]) == 45.0
        assert after_failure.loc["SiO2", "source"] == "major.xlsx"

        del snapshot, orphaned, composition, after_failure
        gc.collect()

    print("rock workspace hardening tests: OK")


if __name__ == "__main__":
    main()
