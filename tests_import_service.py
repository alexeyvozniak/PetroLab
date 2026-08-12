from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pandas as pd

_tmp = tempfile.TemporaryDirectory()
os.environ["PETROLAB_DATA_DIR"] = str(Path(_tmp.name) / "petrolab_data")

from petrolab.db import create_project, get_dataset, load_dataset_dataframe
from petrolab.services.import_service import (
    import_linked_sheets,
    import_uploaded_sheets,
    list_linked_sheets,
    list_uploaded_sheets,
    refresh_dataset_from_source,
)
from petrolab.sources import source_status


def make_workbook(path: Path, value: float = 40.0) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(
            {
                "Sample": ["A", "B"],
                "SiO2": [value, value + 1.0],
                "MgO": [20.0, 19.0],
                "FeO": [5.0, 6.0],
            }
        ).to_excel(writer, sheet_name="Analyses", index=False)
        pd.DataFrame({"Note": ["metadata"]}).to_excel(writer, sheet_name="Notes", index=False)


root = Path(_tmp.name)
linked_path = root / "linked.xlsx"
make_workbook(linked_path)

project_id = create_project("Import service test")
assert list_linked_sheets(linked_path) == ["Analyses", "Notes"]

linked = import_linked_sheets(
    project_id=project_id,
    path=linked_path,
    sheet_names=["Analyses"],
    mineral_key="generic",
    dataset_name="Linked",
    header_row=1,
)
assert linked.count == 1
linked_id = linked.dataset_ids[0]
linked_meta = get_dataset(linked_id)
assert linked_meta["source_kind"] == "linked"
assert linked_meta["sync_enabled"] == 1
assert Path(linked_meta["source_path"]) == linked_path.resolve()

before = load_dataset_dataframe(linked_id, include_meta=True)
assert len(before) == 2
ids_before = before["_analysis_id"].tolist()
assert before["Sample"].tolist() == ["A", "B"]
assert float(before.loc[0, "SiO2"]) == 40.0

make_workbook(linked_path, value=44.0)
status, _ = source_status(get_dataset(linked_id))
assert status == "изменён вне ПетроЛаба"
row_count = refresh_dataset_from_source(linked_id)
assert row_count == 2

after = load_dataset_dataframe(linked_id, include_meta=True)
assert after["_analysis_id"].tolist() == ids_before
assert float(after.loc[0, "SiO2"]) == 44.0
status, _ = source_status(get_dataset(linked_id))
assert status == "актуален"

upload_buffer = io.BytesIO()
with pd.ExcelWriter(upload_buffer, engine="openpyxl") as writer:
    pd.DataFrame({"Sample": ["U1"], "SiO2": [50.0]}).to_excel(
        writer,
        sheet_name="Upload",
        index=False,
    )
upload_bytes = upload_buffer.getvalue()
assert list_uploaded_sheets(upload_bytes, "upload.xlsx") == ["Upload"]

uploaded = import_uploaded_sheets(
    project_id=project_id,
    file_bytes=upload_bytes,
    filename="upload.xlsx",
    sheet_names=["Upload"],
    mineral_key="generic",
    dataset_name="Managed",
    header_row=1,
)
assert uploaded.count == 1
assert uploaded.source_path.exists()
assert "managed_sources" in uploaded.source_path.parts
uploaded_meta = get_dataset(uploaded.dataset_ids[0])
assert uploaded_meta["source_kind"] == "managed_copy"
assert uploaded_meta["sync_enabled"] == 1
assert load_dataset_dataframe(uploaded.dataset_ids[0], include_meta=True)["Sample"].tolist() == ["U1"]

print("import service tests: OK")
_tmp.cleanup()
