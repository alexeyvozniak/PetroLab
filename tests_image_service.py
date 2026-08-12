from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd

_tmp = tempfile.TemporaryDirectory()
os.environ["PETROLAB_DATA_DIR"] = str(Path(_tmp.name) / "petrolab_data")

from petrolab.db import create_project, load_dataset_dataframe
from petrolab.repositories.image_repository import get_image_record
from petrolab.services.image_service import (
    ImagePayload,
    ImageScope,
    SCOPE_ANALYSIS,
    SCOPE_DATASET,
    SCOPE_FIELD,
    create_image_assets,
    delete_image_asset,
    list_dataset_images,
    related_images_for_row,
)
from petrolab.services.import_service import import_linked_sheets

root = Path(_tmp.name)
workbook = root / "images.xlsx"
with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
    pd.DataFrame(
        {
            "Sample": ["A", "A", "B"],
            "Grain": ["1", "1", "2"],
            "Point": ["1", "2", "1"],
            "SiO2": [40.0, 41.0, 42.0],
        }
    ).to_excel(writer, sheet_name="Data", index=False)

project_id = create_project("Images service test")
imported = import_linked_sheets(
    project_id=project_id,
    path=workbook,
    sheet_names=["Data"],
    mineral_key="generic",
    dataset_name="Images",
    header_row=1,
)
dataset_id = imported.dataset_ids[0]
dataframe = load_dataset_dataframe(dataset_id, include_meta=True)
first = dataframe.iloc[0]
analysis_id = str(first["_analysis_id"])

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
    images=[ImagePayload("point.tif", b"point-image")],
    scope=ImageScope(SCOPE_ANALYSIS, analysis_id=analysis_id),
    kind="EDS",
    title="point",
)

assert dataset_result.count == 1
assert field_result.count == 1
assert point_result.count == 1
assert len(list_dataset_images(dataset_id)) == 3
related = related_images_for_row(first, project_id=project_id)
assert {asset["title"] for asset in related} == {"dataset", "grain", "point"}

point_record = get_image_record(point_result.asset_ids[0])
point_path = Path(point_record["stored_path"])
assert point_path.exists()
delete_image_asset(point_result.asset_ids[0])
assert not point_path.exists()
assert len(list_dataset_images(dataset_id)) == 2

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
