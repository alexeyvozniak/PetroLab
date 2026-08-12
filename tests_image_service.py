from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pandas as pd
from PIL import Image

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


def image_bytes(format_name: str) -> bytes:
    """Return a tiny, structurally valid raster for positive image-service tests."""
    buffer = io.BytesIO()
    image = Image.new("RGB", (3, 2), (120, 130, 140))
    image.save(buffer, format=format_name)
    return buffer.getvalue()


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

payload = ImagePayload("bse.png", image_bytes("PNG"))
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
    images=[ImagePayload("grain.jpg", image_bytes("JPEG"))],
    scope=ImageScope(SCOPE_FIELD, scope_column="Grain", scope_value="1"),
    kind="Оптическая микрофотография",
    title="grain",
)
point_result = create_image_assets(
    project_id=project_id,
    dataset_id=dataset_id,
    images=[ImagePayload("points.tif", image_bytes("TIFF"))],
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
            ImagePayload("sample.webp", image_bytes("WEBP")),
            ImageScope(SCOPE_FIELD, scope_column="Sample", scope_value="B"),
            "Фото образца",
            "sample-B",
        ),
        ImageAssignment(
            ImagePayload("point2.jpeg", image_bytes("JPEG")),
            ImageScope(SCOPE_ANALYSIS, analysis_ids=(second_id,)),
            "BSE",
            "single-point",
        ),
    ],
)
assert batch.count == 2
single_point_asset_id = batch.asset_ids[1]
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
assert refresh.detached_image_count == 0
refreshed = load_dataset_dataframe(dataset_id, include_meta=True)
row_a1 = refreshed[(refreshed["Sample"] == "A") & (refreshed["Point"].astype(str) == "1")].iloc[0]
row_a2 = refreshed[(refreshed["Sample"] == "A") & (refreshed["Point"].astype(str) == "2")].iloc[0]
assert str(row_a1["_analysis_id"]) == first_id
assert str(row_a2["_analysis_id"]) == second_id
assert "two-points" in {asset["title"] for asset in related_images_for_row(row_a1, project_id=project_id)}
assert "two-points" in {asset["title"] for asset in related_images_for_row(row_a2, project_id=project_id)}

# Removing A/1/2 must detach its point-specific image links but keep the physical files.
without_second = pd.DataFrame(
    {
        "Sample": ["C", "B", "A"],
        "Grain": ["3", "2", "1"],
        "Point": ["1", "1", "1"],
        "SiO2": [39.0, 42.0, 40.0],
    }
)
with pd.ExcelWriter(workbook, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
    without_second.to_excel(writer, sheet_name="Data", index=False)
removed = refresh_dataset_from_source(dataset_id)
assert removed.removed_count == 1
assert removed.detached_image_count == 2
assert get_image_record(point_result.asset_ids[0])["analysis_ids"] == [first_id]
assert get_image_record(single_point_asset_id)["analysis_ids"] == []
assert Path(get_image_record(single_point_asset_id)["stored_path"]).exists()

point_path = Path(get_image_record(point_result.asset_ids[0])["stored_path"])
assert point_path.exists()
delete_image_asset(point_result.asset_ids[0])
assert not point_path.exists()
assert len(list_dataset_images(dataset_id)) == 4

# Scope validation is tested with a valid image so image-content validation cannot mask it.
try:
    create_image_assets(
        project_id=project_id,
        dataset_id=dataset_id,
        images=[ImagePayload("bad-field.png", image_bytes("PNG"))],
        scope=ImageScope(SCOPE_FIELD, scope_column="Missing", scope_value="X"),
        kind="BSE",
    )
except ValueError as exc:
    assert "Missing" in str(exc)
else:
    raise AssertionError("Unknown field must be rejected")

try:
    create_image_assets(
        project_id=project_id,
        dataset_id=dataset_id,
        images=[ImagePayload("bad.exe", b"not-an-image")],
        scope=ImageScope(SCOPE_DATASET),
        kind="BSE",
    )
except ValueError:
    pass
else:
    raise AssertionError("Unsupported image suffix must be rejected")

# A supported suffix with corrupt/non-image contents must also be rejected.
try:
    create_image_assets(
        project_id=project_id,
        dataset_id=dataset_id,
        images=[ImagePayload("corrupt.png", b"not-a-png")],
        scope=ImageScope(SCOPE_DATASET),
        kind="BSE",
    )
except ValueError as exc:
    assert "изображением" in str(exc) or "поврежд" in str(exc)
else:
    raise AssertionError("Corrupt image contents must be rejected")

# A dataset without Sample/Grain/Point normally has only positional fallback after
# a chemistry edit. Once an image is attached, that guess becomes unsafe and must be
# disabled: the edited row receives a new ID and the old image link is detached.
protected_workbook = root / "protected_identity.xlsx"
with pd.ExcelWriter(protected_workbook, engine="openpyxl") as writer:
    pd.DataFrame({"SiO2": [50.0, 51.0], "MgO": [10.0, 11.0]}).to_excel(
        writer, sheet_name="Data", index=False
    )
protected_dataset = import_linked_sheets(
    project_id=project_id,
    path=protected_workbook,
    sheet_names=["Data"],
    mineral_key="generic",
    dataset_name="Protected identity",
    header_row=1,
).dataset_ids[0]
protected_before = load_dataset_dataframe(protected_dataset, include_meta=True)
protected_old_id = str(protected_before.iloc[0]["_analysis_id"])
protected_asset = create_image_assets(
    project_id=project_id,
    dataset_id=protected_dataset,
    images=[ImagePayload("protected.png", image_bytes("PNG"))],
    scope=ImageScope(SCOPE_ANALYSIS, analysis_ids=(protected_old_id,)),
    kind="BSE",
    title="protected",
).asset_ids[0]
protected_path = Path(get_image_record(protected_asset)["stored_path"])
with pd.ExcelWriter(protected_workbook, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
    pd.DataFrame({"SiO2": [50.5, 51.0], "MgO": [10.0, 11.0]}).to_excel(
        writer, sheet_name="Data", index=False
    )
protected_refresh = refresh_dataset_from_source(protected_dataset)
assert protected_refresh.positional_fallback_disabled
assert protected_refresh.positional_reused_count == 0
assert protected_refresh.reused_count == 1
assert protected_refresh.new_count == 1
assert protected_refresh.removed_count == 1
assert protected_refresh.detached_image_count == 1
protected_after = load_dataset_dataframe(protected_dataset, include_meta=True)
assert str(protected_after.iloc[0]["_analysis_id"]) != protected_old_id
assert get_image_record(protected_asset)["analysis_ids"] == []
assert protected_path.exists()

print("image service tests: OK")
_tmp.cleanup()
