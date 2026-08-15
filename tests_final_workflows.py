from __future__ import annotations

import pandas as pd

from petrolab.ui.pages.thin_section_workspace import _event_point, _event_rectangle, _local_search
from petrolab.ui.work_context import filter_dataframe_to_context


point = _event_point({"x": 25, "y": 50, "width": 100, "height": 200})
assert point == (0.25, 0.25), point

rectangle = _event_rectangle({"x1": 80, "y1": 90, "x2": 20, "y2": 10, "width": 100, "height": 100})
assert rectangle is not None
assert rectangle["kind"] == "region"
assert abs(rectangle["x"] - 0.2) < 1e-9
assert abs(rectangle["y"] - 0.1) < 1e-9
assert abs(rectangle["width"] - 0.6) < 1e-9
assert abs(rectangle["height"] - 0.8) < 1e-9

markers = [
    {"label": "K-17", "note": "rim", "analysis_ids": ["a17"]},
    {"label": "K-18", "note": "core", "analysis_ids": ["a18"]},
]
fields = [
    {"name": "Gr-1", "description": "phlogopite grain", "geometry": {"kind": "grain", "vertices": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]}},
    {"name": "Alteration", "description": "zone", "geometry": {"kind": "region", "x": 0.3, "y": 0.3, "width": 0.2, "height": 0.2}},
]
marker_hits, field_hits = _local_search(markers, fields, "K-17")
assert [item["label"] for item in marker_hits] == ["K-17"]
assert not field_hits
marker_hits, field_hits = _local_search(markers, fields, "phlogopite")
assert not marker_hits
assert [item["name"] for item in field_hits] == ["Gr-1"]

frame = pd.DataFrame([
    {"_analysis_id": "a1", "_dataset_id": 1, "Sample": "KIV-2"},
    {"_analysis_id": "a2", "_dataset_id": 2, "Sample": "PG-6"},
])
assert filter_dataframe_to_context(frame, {"analysis_ids": ["a2"]})["_analysis_id"].tolist() == ["a2"]
assert filter_dataframe_to_context(frame, {"dataset_ids": [1]})["_analysis_id"].tolist() == ["a1"]
assert filter_dataframe_to_context(frame, {"sample": "kiv-2"})["_analysis_id"].tolist() == ["a1"]

print("final workflow tests: OK")
