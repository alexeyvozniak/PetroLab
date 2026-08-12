from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pandas as pd

_tmp = tempfile.TemporaryDirectory()
os.environ["PETROLAB_DATA_DIR"] = str(Path(_tmp.name) / "petrolab_data")

from petrolab.db import create_project, load_dataset_dataframe
from petrolab.repositories.image_repository import get_image_record
from petrolab.services.image_service import (
    ImageAssignment,
    ImagePayload,
    ImageScope,
    SCOPE_ANALYSIS,
    SCOPE_DATASET,
    SCOPE_FIELD,
    create_assigned_image_batch,
    create_image_assets,
    delete_image_asset,
    image_export_records,
    list_dataset_images,
    related_images_for_row,
)
from petrolab.services.import_service import import_linked_sheets, refresh_dataset_from_source

root = Path(_tmp.name)
workbook = root / "images.xlsx"
initial = pd.DataFrame(
    {
        "Sample": ["A", "A", "B"],
        "Grain": ["1", "1", "2"],
        "Point": ["1", "2", "1"],
        "SiO2": [40.0, 41.0, 42.0],
    }
)
with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
    initial.to_excel(writer, sheet_name="Data", index=False)

project_id = create_project("Images service test")
imported = import_linked_sheets(
    project_id=project_id,
    path=workbook,
    sheet_names=["Data"],
    mineral_key="generic",
    dataset_name="Images",
    header_row=1,
    semantic_maps={"Data": {"Sample": "Sample", "Grain": "Grain", "Point": "Point"}},
)
dataset_id = imported.dataset_ids[0]
dataframe = load_dataset_dataframe(dataset_id, include_meta=True)
first = dataframe.iloc[0]
second = dataframe.iloc[1]
first_id = str(first["_analysis_id"])
second_id = str(second["_analysis_id"])

payload = ImagePayload("bse.png", b"fake-image-bytes")
dataset_result = create_image_assets(
    project_id=project_id,
    dataset_id=dataset_id,
    images=[payload],
    scope=ImageScope(SCOPE_DATASET),
    kind="BSE",
    title="dataset",
)
field_result = create_image_assets(
    project_id=project_id,
    dataset_id=dataset_id,
    images=[ImagePayload("grain.jpg", b"field-image")],
    scope=ImageScope(SCOPE_FIELD, scope_column="Grain", scope_value="1"),
    kind="Оптическая микрофотография",
    title="grain",
)
point_result = create_image_assets(
    project_id=project_id,
    dataset_id=dataset_id,
    images=[ImagePayload("points.tif", b"point-image")],
    scope=ImageScope(SCOPE_ANALYSIS, analysis_ids=(first_id, second_id)),
    kind="EDS",
    title="two-points",
)

assert dataset_result.count == 1
assert field_result.count == 1
assert point_result.count == 1
assert len(list_dataset_images(dataset_id)) == 3
point_record = get_image_record(point_result.asset_ids[0])
assert set(point_record["analysis_ids"]) == {first_id, second_id}

# Multi-point metadata must remain exportable to XLSX; raw Python lists are not valid Excel cells.
export_records = image_export_records()
export_row = next(row for row in export_records if int(row["id"]) == point_result.asset_ids[0])
assert isinstance(export_row["analysis_ids"], str)
assert first_id in export_row["analysis_ids"] and second_id in export_row["analysis_ids"]
export_buffer = io.BytesIO()
with pd.ExcelWriter(export_buffer, engine="openpyxl") as writer:
    pd.DataFrame(export_records).to_excel(writer, index=False, sheet_name="Изображения")
assert export_buffer.getvalue().startswith(b"PK")

related_first = related_images_for_row(first, project_id=project_id)
related_second = related_images_for_row(second, project_id=project_id)
assert {asset["title"] for asset in related_first} == {"dataset", "grain", "two-points"}
assert {asset["title"] for asset in related_second} == {"dataset", "grain", "two-points"}

# Per-image assignments can differ inside one atomic batch.
batch = create_assigned_image_batch(
    project_id=project_id,
    dataset_id=dataset_id,
    assignments=[
        ImageAssignment(
            ImagePayload("sample.webp", b"sample"),
            ImageScope(SCOPE_FIELD, scope_column="Sample", scope_value="B"),
            "Фото образца",
            "sample-B",
        ),
        ImageAssignment(
            ImagePayload("point2.jpeg", b"point2"),
            ImageScope(SCOPE_ANALYSIS, analysis_ids=(second_id,)),
            "BSE",
            "single-point",
        ),
    ],
)
assert batch.count == 2
assert len(list_dataset_images(dataset_id)) == 5

# Sorting rows and inserting a new point must preserve old IDs and image links.
reordered = pd.DataFrame(
    {
        "Sample": ["C", "B", "A", "A"],
        "Grain": ["3", "2", "1", "1"],
        "Point": ["1", "1", "2", "1"],
        "SiO2": [39.0, 42.0, 41.0, 40.0],
    }
)
with pd.ExcelWriter(workbook, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
    reordered.to_excel(writer, sheet_name="Data", index=False)
refresh = refresh_dataset_from_source(dataset_id)
assert refresh.moved_rows_detected
assert refresh.reused_count == 3
assert refresh.new_count == 1
refreshed = load_dataset_dataframe(dataset_id, include_meta=True)
row_a1 = refreshed[(refreshed["Sample"] == "A") & (refreshed["Point"].astype(str) == "1")].iloc[0]
row_a2 = refreshed[(refreshed["Sample"] == "A") & (refreshed["Point"].astype(str) == "2")].iloc[0]
assert str(row_a1["_analysis_id"]) == first_id
assert str(row_a2["_analysis_id"]) == second_id
assert "two-points" in {asset["title"] for asset in related_images_for_row(row_a1, project_id=project_id)}
assert "two-points" in {asset["title"] for asset in related_images_for_row(row_a2, project_id=project_id)}

point_path = Path(get_image_record(point_result.asset_ids[0])["stored_path"])
assert point_path.exists()
delete_image_asset(point_result.asset_ids[0])
assert not point_path.exists()
assert len(list_dataset_images(dataset_id)) == 4

try:
    create_image_assets(
        project_id=project_id,
        dataset_id=dataset_id,
        images=[ImagePayload("bad.png", b"x")],
        scope=ImageScope(SCOPE_FIELD, scope_column="Missing", scope_value="X"),
        kind="BSE",
    )
except ValueError:
    pass
else:
    raise AssertionError("Unknown field must be rejected")

try:
    create_image_assets(
        project_id=project_id,
        dataset_id=dataset_id,
        images=[ImagePayload("bad.exe", b"x")],
        scope=ImageScope(SCOPE_DATASET),
        kind="BSE",
    )
except ValueError:
    pass
else:
    raise AssertionError("Unsupported image suffix must be rejected")

print("image service tests: OK")
_tmp.cleanup()