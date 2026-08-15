from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd

from petrolab.composite_points import set_physical_point_links
from petrolab.measurement_registry import create_entity
from petrolab.ui.work_context import filter_dataframe_to_context
from tests_v0151_silent_errors import Workspace


def test_explicit_thin_section_link_survives_raw_sample_alias_mismatch():
    with tempfile.TemporaryDirectory() as tmp, Workspace(Path(tmp)) as ws:
        ws.add_dataset(16, [("alias-1", {"Sample": "RAW_ALIAS", "MgO": 20.0})])
        section = create_entity(ws.project_id, kind="thin_section", name="TS-alias")
        point = create_entity(ws.project_id, kind="probe_point", name="P-alias", parent_id=section)
        set_physical_point_links(ws.project_id, point, ["alias-1"])
        frame = pd.DataFrame([
            {"_analysis_id": "alias-1", "_dataset_id": 16, "Sample": "RAW_ALIAS"},
        ])
        context = {
            "project_id": ws.project_id,
            "thin_section_id": section,
            "sample": "CANONICAL_SAMPLE_NAME",
            "analysis_ids": [],
            "dataset_ids": [16],
        }
        result = filter_dataframe_to_context(frame, context)
        assert result["_analysis_id"].tolist() == ["alias-1"]


if __name__ == "__main__":
    test_explicit_thin_section_link_survives_raw_sample_alias_mismatch()
    print("v0.15.1 thin-section alias context: OK")
