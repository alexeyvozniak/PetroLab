from __future__ import annotations

import os
import shutil
import tempfile
from io import BytesIO
from pathlib import Path

import pandas as pd
from PIL import Image


ROOT = Path(tempfile.mkdtemp(prefix="petrolab_linked_petrography_"))
os.environ["PETROLAB_DATA_DIR"] = str(ROOT / "data")

from petrolab.db import add_dataset, create_project, load_dataset_dataframe, replace_dataset_rows
from petrolab.linked_petrography import dataset_ids_for_analysis_ids, related_thin_section_markers
from petrolab.measurement_registry import create_entity
from petrolab.slides import create_slide_marker, register_managed_slide_image
from petrolab.storage import ensure_storage


def _dataset(project_id: int, *, name: str, source: str, frame: pd.DataFrame) -> tuple[int, list[str]]:
    csv_path = ROOT / f"{source}.csv"
    frame.to_csv(csv_path, index=False)
    dataset_id = add_dataset(
        project_id,
        name,
        "mica",
        f"{source}.xlsx",
        "Sheet1",
        f"{source}-sha",
        str(csv_path),
        len(frame),
    )
    replace_dataset_rows(dataset_id, frame, source_rows=list(range(2, len(frame) + 2)))
    loaded = load_dataset_dataframe(dataset_id, include_meta=True)
    return dataset_id, loaded["_analysis_id"].astype(str).tolist()


def main() -> None:
    try:
        ensure_storage()
        project_id = create_project("Linked petrography", "CI-only physical/chemical round trip")
        epma_dataset, epma_ids = _dataset(
            project_id,
            name="KIV EPMA",
            source="kiv_epma",
            frame=pd.DataFrame(
                {
                    "Sample": ["KIV-2", "KIV-2"],
                    "Point": ["P-1-EPMA", "P-2-EPMA"],
                    "SiO2": [40.1, 39.8],
                    "Al2O3": [13.5, 14.1],
                    "TiO2": [2.1, 1.7],
                }
            ),
        )
        la_dataset, la_ids = _dataset(
            project_id,
            name="KIV LA-ICP-MS",
            source="kiv_la",
            frame=pd.DataFrame(
                {
                    "Sample": ["KIV-2"],
                    "Point": ["P-1-LA"],
                    "SiO2": [40.2],
                    "Al2O3": [13.7],
                    "TiO2": [2.2],
                    "Rb [µg/g]": [520.0],
                }
            ),
        )
        assert len(epma_ids) == 2 and len(la_ids) == 1
        p1_ids = (epma_ids[0], la_ids[0])
        assert len(set(p1_ids)) == 2

        section_id = create_entity(project_id, kind="thin_section", name="KIV-2-1")
        buffer = BytesIO()
        Image.new("RGB", (600, 400), "white").save(buffer, format="PNG")
        image = register_managed_slide_image(
            project_id,
            filename="KIV-2-1_BSE.png",
            data=buffer.getvalue(),
            title="KIV-2-1 BSE",
            image_type="BSE",
            thin_section_id=section_id,
        )
        marker_id = create_slide_marker(
            project_id,
            slide_image_id=image.id,
            x_norm=0.42,
            y_norm=0.57,
            label="P-1",
            analysis_ids=p1_ids,
        )
        create_slide_marker(
            project_id,
            slide_image_id=image.id,
            x_norm=0.75,
            y_norm=0.30,
            label=epma_ids[0],  # same text is not a relationship
            analysis_ids=(epma_ids[1],),
        )

        links = related_thin_section_markers(project_id, (epma_ids[0],))
        assert len(links) == 1
        assert links[0].marker_id == marker_id
        assert len(links[0].analysis_ids) == 2
        assert set(links[0].analysis_ids) == set(p1_ids)
        assert links[0].thin_section_id == section_id
        assert links[0].slide_image_id == image.id
        assert dataset_ids_for_analysis_ids(project_id, p1_ids) == tuple(sorted((epma_dataset, la_dataset)))
        print("PetroLab linked petrography multi-dataset storage round trip: OK")
    finally:
        shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
