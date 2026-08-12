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
        # The fully empty middle row is a common visual separator in old laboratory tables.
        # It must not become an analysis, but B must still remember that it lives on Excel row 4.
        pd.DataFrame(
            {
                "Sample": ["A", None, "B"],
                "Point": ["1", None, "2"],
                "SiO2": [value, None, value + 1.0],
                "MgO": [20.0, None, 19.0],
                "FeO": [5.0, None, 6.0],
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
    semantic_maps={"Analyses": {"Sample": "Sample", "Point": "Point"}},
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
assert before["_source_row"].astype(int).tolist() == [2, 4]
assert float(before.loc[0, "SiO2"]) == 40.0

make_workbook(linked_path, value=44.0)
status, _ = source_status(get_dataset(linked_id))
assert status == "изменён вне ПетроЛаба"
refresh = refresh_dataset_from_source(linked_id)
assert refresh.row_count == 2
assert refresh.reused_count == 2
assert refresh.new_count == 0
assert refresh.removed_count == 0
assert refresh.positional_reused_count == 0

after = load_dataset_dataframe(linked_id, include_meta=True)
assert after["_analysis_id"].tolist() == ids_before
assert after["_source_row"].astype(int).tolist() == [2, 4]
assert float(after.loc[0, "SiO2"]) == 44.0
status, _ = source_status(get_dataset(linked_id))
assert status == "актуален"

# A legacy table without Sample/Grain/Point can only preserve a changed row by its
# physical position when row count/order is stable. The result must expose that low confidence.
positional_path = root / "positional.xlsx"
with pd.ExcelWriter(positional_path, engine="openpyxl") as writer:
    pd.DataFrame({"SiO2": [50.0, 51.0], "MgO": [10.0, 11.0]}).to_excel(
        writer, sheet_name="Data", index=False
    )
positional_id = import_linked_sheets(
    project_id=project_id,
    path=positional_path,
    sheet_names=["Data"],
    mineral_key="generic",
    dataset_name="Positional",
    header_row=1,
).dataset_ids[0]
positional_before = load_dataset_dataframe(positional_id, include_meta=True)
with pd.ExcelWriter(positional_path, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
    pd.DataFrame({"SiO2": [50.5, 51.0], "MgO": [10.0, 11.0]}).to_excel(
        writer, sheet_name="Data", index=False
    )
positional_refresh = refresh_dataset_from_source(positional_id)
assert positional_refresh.reused_count == 2
assert positional_refresh.positional_reused_count == 1
assert not positional_refresh.positional_fallback_disabled
assert not positional_refresh.moved_rows_detected
positional_after = load_dataset_dataframe(positional_id, include_meta=True)
assert positional_after["_analysis_id"].tolist() == positional_before["_analysis_id"].tolist()

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
