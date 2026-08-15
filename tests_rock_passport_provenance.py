from __future__ import annotations

import gc
import os
import tempfile
from pathlib import Path

import pandas as pd


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_rock_passport_", ignore_cleanup_errors=True) as tmp:
        os.environ["PETROLAB_DATA_DIR"] = str(Path(tmp) / "data")
        from petrolab.db import create_project
        from petrolab.repositories.rock_repository import get_rock
        from petrolab.services.rock_service import import_rocks_wide
        from petrolab.storage import ensure_storage

        ensure_storage()
        project_id = create_project("Passport provenance", "")
        first = import_rocks_wide(
            pd.DataFrame({"Rock": ["R1"], "SiO2": [45.0], "MgO": [12.0]}),
            project_id=project_id,
            name_column="Rock",
            chemistry_method="XRF",
            laboratory="Lab XRF",
            source="major.xlsx",
            on_conflict="update",
        )
        rock_id = int(first.created_ids[0])
        import_rocks_wide(
            pd.DataFrame({"Rock": ["R1"], "La ppm": [100.0]}),
            project_id=project_id,
            name_column="Rock",
            chemistry_method="LA-ICP-MS",
            laboratory="Lab ICP",
            source="trace.xlsx",
            on_conflict="update",
        )
        rock = get_rock(rock_id)
        assert rock["chemistry_method"] == "XRF | LA-ICP-MS"
        assert rock["laboratory"] == "Lab XRF | Lab ICP"

        # Repeating the same metadata must not accumulate duplicates.
        import_rocks_wide(
            pd.DataFrame({"Rock": ["R1"], "Ce ppm": [200.0]}),
            project_id=project_id,
            name_column="Rock",
            chemistry_method="LA-ICP-MS",
            laboratory="Lab ICP",
            source="trace2.xlsx",
            on_conflict="update",
        )
        rock = get_rock(rock_id)
        assert rock["chemistry_method"] == "XRF | LA-ICP-MS"
        assert rock["laboratory"] == "Lab XRF | Lab ICP"
        del rock
        gc.collect()

    print("rock passport provenance tests: OK")


if __name__ == "__main__":
    main()
