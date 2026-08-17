from __future__ import annotations

import pandas as pd

from petrolab.ui.cluster_plot_handoff import cluster_label, seed_cluster_plot_handoff
from petrolab.ui.pages.v0160_cluster_xy_hotfix import apply_plot_overlays
from petrolab.ui.smart_plot_start import consume_plot_scope


state: dict = {}
dataset_ids = [11, 12]
analysis_ids = ["a-1", "a-2", "a-3", "a-4"]
cluster_by_id = {"a-1": 0, "a-2": 0, "a-3": 1, "a-4": -1}

seeded_datasets, seeded_ids = seed_cluster_plot_handoff(
    state,
    dataset_ids=dataset_ids,
    analysis_ids=analysis_ids,
    cluster_by_analysis_id=cluster_by_id,
)
assert seeded_datasets == (11, 12)
assert seeded_ids == tuple(analysis_ids)
context = state["workflow_plot_context"]
assert context["preferred_group"] == "Cluster"
assert context["overlay_columns"]["Cluster"] == {
    "a-1": "Cluster 1",
    "a-2": "Cluster 1",
    "a-3": "Cluster 2",
    "a-4": "Шум / −1",
}
assert cluster_label(-1) == "Шум / −1"
assert cluster_label(2) == "Cluster 3"
assert "Generation" not in context and "Work Group" not in context

# Streamlit reruns consume the incoming handoff but must persist the exact overlay
# in the canonical plot context instead of losing cluster identities after one click.
scope = consume_plot_scope(
    state,
    project_id=7,
    available_dataset_ids=[11, 12, 13],
    work_context=None,
)
assert scope.dataset_ids == (11, 12)
assert scope.analysis_ids == tuple(analysis_ids)
persisted = state["_petrolab_plot_scope_context"]
assert persisted["preferred_group"] == "Cluster"
assert persisted["overlay_columns"]["Cluster"]["a-3"] == "Cluster 2"

raw = pd.DataFrame(
    {
        "_analysis_id": ["a-1", "a-2", "a-3", "a-4", "other"],
        "SiO2": [40.0, 41.0, 42.0, 43.0, 50.0],
    }
)
raw_copy = raw.copy(deep=True)
overlaid = apply_plot_overlays(raw, persisted)
assert overlaid["Cluster"].tolist()[:4] == ["Cluster 1", "Cluster 1", "Cluster 2", "Шум / −1"]
assert pd.isna(overlaid.loc[4, "Cluster"])
pd.testing.assert_frame_equal(raw, raw_copy)

print("cluster to XY handoff: OK")
