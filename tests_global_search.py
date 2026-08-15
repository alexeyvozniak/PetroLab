from __future__ import annotations

import pandas as pd

from petrolab.source_registry import SOURCE_LABEL_COLUMN
from petrolab.ui.pages.global_search import _literal_search


dataframe = pd.DataFrame([
    {
        "Sample": "PG-15",
        "Grain": "1",
        "Point": "1",
        "Минерал": "apatite",
        "Generation": "rim",
        "Method": "LA-ICP-MS",
        "Набор": "Apatite trace",
        SOURCE_LABEL_COLUMN: "Reguir et al., 2009",
        "_analysis_id": "a1",
        "_dataset_id": 1,
    },
    {
        "Sample": "KIV-2",
        "Grain": "2",
        "Point": "3",
        "Минерал": "mica",
        "Generation": "core",
        "Method": "EPMA-WDS",
        "Набор": "Kandalaksha mica",
        SOURCE_LABEL_COLUMN: "Own data",
        "_analysis_id": "a2",
        "_dataset_id": 2,
    },
])

assert _literal_search(dataframe, "apatite")["_analysis_id"].tolist() == ["a1"]
assert _literal_search(dataframe, "Reguir")["_analysis_id"].tolist() == ["a1"]
assert _literal_search(dataframe, "Kandalaksha")["_analysis_id"].tolist() == ["a2"]
assert _literal_search(dataframe, "LA-ICP-MS")["_analysis_id"].tolist() == ["a1"]
# Search is intentionally literal, not regex-driven.
assert _literal_search(dataframe, "[").empty

print("global search tests: OK")
