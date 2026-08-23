from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pandas as pd

_tmp = tempfile.TemporaryDirectory()
os.environ["PETROLAB_DATA_DIR"] = str(Path(_tmp.name) / "petrolab_data")

from petrolab.db import create_project, get_dataset, load_dataset_dataframe
from petrolab.services.import_service import import_uploaded_sheets


def run() -> None:
    workbook = io.BytesIO()
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        # This is deliberately not a rectangular workbook: it contains notes,
        # an empty separator and two unrelated tables in one worksheet.
        pd.DataFrame([
            ["Laboratory note", None, None],
            [None, None, None],
            ["Sample", "Point", "SiO2"],
            ["A", "1", 40.0],
            ["B", "2", 41.0],
            [None, None, None],
            ["Second table", None, None],
            ["Specimen", "Spot", "MgO"],
            ["C", "3", 20.0],
            ["D", "4", 19.0],
        ]).to_excel(writer, sheet_name="Unsorted", index=False, header=False)

    project_id = create_project("Manual block import")
    result = import_uploaded_sheets(
        project_id=project_id,
        file_bytes=workbook.getvalue(),
        filename="unsorted.xlsx",
        sheet_names=[],
        mineral_key="generic",
        dataset_name="Unsorted workbook",
        header_row=1,
        blocks=[
            {
                "id": "major",
                "sheet": "Unsorted",
                "title": "Основные оксиды",
                "header_row": 3,
                "last_row": 5,
                "mineral_key": "generic",
            },
            {
                "id": "trace",
                "sheet": "Unsorted",
                "title": "Вторая таблица",
                "header_row": 8,
                "last_row": 10,
                "mineral_key": "generic",
            },
        ],
        semantic_maps={
            "major": {"Sample": "Sample", "Point": "Point"},
            "trace": {"Sample": "Specimen", "Point": "Spot"},
        },
    )

    assert result.count == 2
    first = load_dataset_dataframe(result.dataset_ids[0], include_meta=True)
    second = load_dataset_dataframe(result.dataset_ids[1], include_meta=True)
    assert first["Sample"].tolist() == ["A", "B"]
    assert first["_source_row"].astype(int).tolist() == [4, 5]
    assert second["Sample"].tolist() == ["C", "D"]
    assert second["_source_row"].astype(int).tolist() == [9, 10]
    # Automatic refresh is intentionally disabled for a hand-cut fragment: an
    # inserted note above it must never silently shift the imported table.
    assert get_dataset(result.dataset_ids[0])["sync_enabled"] == 0


try:
    run()
    print("manual import block tests: OK")
finally:
    _tmp.cleanup()
