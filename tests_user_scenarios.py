"""Regression tests for the cross-workspace user journeys added in v0.16."""
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pandas as pd
from PIL import Image

_tmp = tempfile.TemporaryDirectory(prefix="petrolab_scenarios_")
os.environ["PETROLAB_DATA_DIR"] = str(Path(_tmp.name) / "data")

from petrolab.db import add_dataset, create_project, load_dataset_dataframe, replace_dataset_rows
from petrolab.figure_recipes import list_figure_recipes, save_figure_recipe
from petrolab.image_inbox import add_to_inbox, assign_inbox_item, list_inbox_items
from petrolab.search import global_search
from petrolab.selections import list_selections, save_selection, selection_analysis_ids
from petrolab.services.image_service import ImageAssignment, ImagePayload, ImageScope, SCOPE_ANALYSIS
from petrolab.slides import (
    attach_image_to_slide_field,
    create_slide_field,
    list_field_images,
    register_managed_slide_image,
)


def image_bytes() -> bytes:
    buffer = io.BytesIO()
    with Image.new("RGB", (8, 6), "gray") as image:
        image.save(buffer, format="PNG")
    return buffer.getvalue()


def main() -> None:
    root = Path(_tmp.name)
    project_id = create_project("Scenario project")
    csv_path = root / "rows.csv"
    frame = pd.DataFrame({"Sample": ["PG-12", "PG-13"], "Mineral": ["apatite", "mica"], "Point": ["P1", "P2"], "SiO2": [40.0, 41.0]})
    frame.to_csv(csv_path, index=False)
    dataset_id = add_dataset(project_id, "Kandalaksha apatite", "apatite", "data.xlsx", "Sheet1", "test", str(csv_path), len(frame))
    replace_dataset_rows(dataset_id, frame, source_rows=[2, 3])
    loaded = load_dataset_dataframe(dataset_id, include_meta=True)
    first_id = str(loaded.iloc[0]["_analysis_id"])

    selection_id = save_selection(project_id, name="Apatite selection", analysis_ids=[first_id], note="Figure check", context={"source": "test"})
    assert selection_analysis_ids(selection_id) == [first_id]
    assert list_selections(project_id)[0]["member_count"] == 1

    results = global_search("PG-12")
    assert any(item["kind"] == "analysis" and item["analysis_id"] == first_id for item in results)

    inbox = add_to_inbox(project_id, [ImagePayload("BSE-03.png", image_bytes())])
    assert len(inbox) == 1 and len(list_inbox_items(project_id)) == 1
    asset_id = assign_inbox_item(
        project_id, inbox[0].id, dataset_id=dataset_id,
        assignment=ImageAssignment(ImagePayload("BSE-03.png", image_bytes()), ImageScope(SCOPE_ANALYSIS, analysis_ids=(first_id,)), "BSE", "BSE-03"),
    )
    assert asset_id > 0 and list_inbox_items(project_id) == []

    main_slide = register_managed_slide_image(project_id, filename="PPL.png", data=image_bytes(), title="PPL", image_type="Фотография шлифа")
    bse_slide = register_managed_slide_image(project_id, filename="BSE.png", data=image_bytes(), title="BSE-03", image_type="BSE")
    field_id = create_slide_field(project_id, slide_image_id=main_slide.id, name="Поле 3", geometry={"x": 0.1, "y": 0.1, "width": 0.2, "height": 0.2})
    attach_image_to_slide_field(project_id, field_id=field_id, image_id=bse_slide.id)
    assert [image.id for image in list_field_images(project_id, field_id=field_id)] == [bse_slide.id]

    recipe_id = save_figure_recipe(project_id, name="Mixed figure", layout_name="2 × 1", cells=[
        {"position": "A", "type": "XY", "reference": "Mica XY", "caption": "A"},
        {"position": "B", "type": "Треугольная", "reference": "Mica ternary", "caption": "B"},
    ])
    assert recipe_id > 0 and list_figure_recipes(project_id)[0]["cells"][1]["type"] == "Треугольная"
    print("user scenario tests: OK")


if __name__ == "__main__":
    try:
        main()
    finally:
        _tmp.cleanup()
