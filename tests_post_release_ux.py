from __future__ import annotations

import os
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

import pandas as pd
from PIL import Image


ROOT = Path(tempfile.mkdtemp(prefix="petrolab_post_release_ux_"))
os.environ["PETROLAB_DATA_DIR"] = str(ROOT / "data")

from petrolab.db import add_dataset, create_project, load_dataset_dataframe, replace_dataset_rows
from petrolab.phase_suggestions import materialize_confirmed_phases
from petrolab.repositories.image_repository import get_image_record
from petrolab.services.image_service import ImageAssignment, ImagePayload, ImageScope, SCOPE_ANALYSIS
from petrolab.services.source_sheet_image_service import create_source_sheet_image_batch
from petrolab.source_sheet_scope import list_source_sheet_scopes, load_source_sheet_universe
from petrolab.storage import ensure_storage
from petrolab.ui.pages.v0160_phase_queue_hotfix import _nested_split_pairs, _ordered_candidates, _reviewable
from petrolab.ui.source_sheet_image_wizard import _draft_prefix


def _dataset(project_id: int, name: str, sheet: str, frame: pd.DataFrame) -> tuple[int, list[str]]:
    path = ROOT / f"{name.replace(' ', '_')}_{sheet}.csv"
    frame.to_csv(path, index=False)
    dataset_id = add_dataset(
        project_id,
        name,
        "generic",
        "session.xlsx",
        sheet,
        "session-sha",
        str(path),
        len(frame),
    )
    replace_dataset_rows(dataset_id, frame, source_rows=list(range(2, len(frame) + 2)))
    loaded = load_dataset_dataframe(dataset_id, include_meta=True)
    return dataset_id, loaded["_analysis_id"].astype(str).tolist()


def _png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (80, 60), "white").save(buffer, format="PNG")
    return buffer.getvalue()


def main() -> None:
    try:
        ensure_storage()
        project_id = create_project("UX regression", "source-sheet scope")
        source_id, ids = _dataset(
            project_id,
            "Session",
            "Sheet 1",
            pd.DataFrame(
                {
                    "Sample": ["19", "19", "19", "19"],
                    "Point": ["P1", "P2", "P3", "P4"],
                    "SiO2": [39.0, 0.4, 41.2, 52.0],
                    "FeOt": [9.0, 91.0, 12.0, 8.0],
                    "TiO2": [2.0, 1.2, 3.0, 0.4],
                }
            ),
        )
        second_id, second_ids = _dataset(
            project_id,
            "Session",
            "Sheet 2",
            pd.DataFrame({"Sample": ["20"], "Point": ["Q1"], "SiO2": [40.0], "FeOt": [10.0], "TiO2": [2.0]}),
        )

        # Split two rows into different phase datasets. The physical/source-sheet
        # universe must remain the original four analysis ids.
        created = materialize_confirmed_phases(
            source_id,
            {ids[0]: "phlogopite", ids[1]: "magnetite"},
        )
        assert set(created) == {"phlogopite", "magnetite"}
        scopes = list_source_sheet_scopes(project_id)
        sheet1 = next(scope for scope in scopes if scope.source_sheet == "Sheet 1")
        sheet2 = next(scope for scope in scopes if scope.source_sheet == "Sheet 2")
        assert sheet1.row_count == 4
        assert sheet2.row_count == 1
        universe = load_source_sheet_universe(project_id, sheet1)
        assert set(universe["_analysis_id"].astype(str)) == set(ids)
        phase_by_id = dict(zip(universe["_analysis_id"].astype(str), universe["Подтверждённая фаза"].astype(str)))
        assert phase_by_id[ids[0]] == "phlogopite"
        assert phase_by_id[ids[1]] == "magnetite"

        # One image may link analyses that now live in two different phase datasets,
        # because they still belong to the same immutable source sheet.
        assignment = ImageAssignment(
            ImagePayload("sheet1.png", _png_bytes()),
            ImageScope(SCOPE_ANALYSIS, analysis_ids=(ids[0], ids[1])),
            "BSE",
            "Sheet 1 BSE",
        )
        result = create_source_sheet_image_batch(
            project_id=project_id,
            anchor_dataset_id=sheet1.anchor_dataset_id,
            assignments=[assignment],
        )
        record = get_image_record(result.asset_ids[0])
        assert set(record["analysis_ids"]) == {ids[0], ids[1]}

        # Cross-sheet contamination must still be rejected.
        bad = ImageAssignment(
            ImagePayload("bad.png", _png_bytes()),
            ImageScope(SCOPE_ANALYSIS, analysis_ids=(ids[0], second_ids[0])),
            "BSE",
            "bad",
        )
        rejected = False
        try:
            create_source_sheet_image_batch(
                project_id=project_id,
                anchor_dataset_id=sheet1.anchor_dataset_id,
                assignments=[bad],
            )
        except ValueError:
            rejected = True
        assert rejected

        # Draft namespaces are stable for the same photo+sheet and different for
        # another sheet: switching sheets cannot overwrite the previous draft.
        prefix_1a = _draft_prefix("batch", "photo.png", b"123", sheet1)
        prefix_1b = _draft_prefix("batch", "photo.png", b"123", sheet1)
        prefix_2 = _draft_prefix("batch", "photo.png", b"123", sheet2)
        assert prefix_1a == prefix_1b
        assert prefix_1a != prefix_2

        # Normal review queue accepts only generic/mixed datasets. A phase child is
        # never offered again as a fresh phase-review source.
        rows = [
            {"id": 1, "name": "Book · Неразобранные / mixed", "mineral_key": "generic", "row_count": 4, "source_sha256": "x", "source_filename": "book.xlsx"},
            {"id": 2, "name": "Book · phlogopite", "mineral_key": "mica", "row_count": 5, "source_sha256": "x", "source_filename": "book.xlsx"},
            {"id": 3, "name": "Book Sheet 2", "mineral_key": "generic", "row_count": 8, "source_sha256": "x", "source_filename": "book.xlsx"},
        ]
        assert _reviewable(rows[0])
        assert not _reviewable(rows[1])
        queue = _ordered_candidates(rows, completed={1}, after_dataset_id=1)
        assert [int(item["id"]) for item in queue] == [3]

        nested = [
            {"id": 10, "name": "Book · phlogopite", "mineral_key": "mica", "row_count": 5, "source_sha256": "x", "source_sheet": "S"},
            {"id": 11, "name": "Book · phlogopite · phlogopite", "mineral_key": "mica", "row_count": 5, "source_sha256": "x", "source_sheet": "S"},
        ]
        pairs = _nested_split_pairs(nested)
        assert [(int(child["id"]), int(parent["id"])) for child, parent in pairs] == [(11, 10)]

        print("PetroLab post-release UX: source-sheet links, queue progression and draft isolation: OK")
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
