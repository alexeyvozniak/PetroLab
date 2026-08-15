from __future__ import annotations

import io
import tempfile
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import pandas as pd

import petrolab.db as db
from petrolab.services import import_service
from petrolab.storage import ensure_storage


def test_real_runtime_upload_persists_wds_method():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        data_dir = root / "data"
        with ExitStack() as stack:
            stack.enter_context(patch.object(db, "DATA_DIR", data_dir))
            stack.enter_context(patch.object(db, "DB_PATH", data_dir / "petrolab.sqlite3"))
            stack.enter_context(patch.object(db, "ASSETS_DIR", data_dir / "assets"))
            stack.enter_context(patch.object(db, "BACKUPS_DIR", data_dir / "backups"))
            stack.enter_context(patch.object(import_service, "DATA_DIR", data_dir))
            ensure_storage()
            project_id = db.create_project("Runtime WDS")

            source = pd.DataFrame({
                "No.": [1, 2],
                "SiO2": [40.0, 41.0],
                "Al2O3": [15.0, 14.5],
                "FeO": [8.0, 7.5],
                "MgO": [20.0, 20.5],
                "Comment": ["S1 1", "S1 2"],
            })
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                source.to_excel(writer, sheet_name="Probe", index=False)

            result = import_service.import_uploaded_sheets(
                project_id=project_id,
                file_bytes=buffer.getvalue(),
                filename="wds.xlsx",
                sheet_names=["Probe"],
                mineral_key="generic",
                dataset_name="WDS",
                header_row=1,
                semantic_maps={"Probe": {}},
                measurement_maps={"Probe": {"FeO": "FeO"}},
                header_rows={"Probe": 1},
                mineral_keys={"Probe": "generic"},
            )
            assert len(result.dataset_ids) == 1
            frame = db.load_dataset_dataframe(int(result.dataset_ids[0]), include_meta=True)
            assert frame["Method"].tolist() == ["EPMA-WDS", "EPMA-WDS"]
            assert frame["Sample"].tolist() == ["S1", "S1"]
            assert frame["Point"].astype(str).tolist() == ["1", "2"]


if __name__ == "__main__":
    test_real_runtime_upload_persists_wds_method()
    print("v0.15.1 runtime import E2E: OK")
