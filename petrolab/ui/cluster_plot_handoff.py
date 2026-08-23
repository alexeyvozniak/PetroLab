from __future__ import annotations

from collections.abc import Iterable, Mapping, MutableMapping
from typing import Any

from petrolab.ui.smart_plot_start import seed_plot_handoff


CLUSTER_OVERLAY_COLUMN = "Cluster"


def cluster_label(value: int) -> str:
    number = int(value)
    return "Шум / −1" if number == -1 else f"Cluster {number + 1}"


def seed_cluster_plot_handoff(
    state: MutableMapping[str, Any],
    *,
    dataset_ids: Iterable[Any],
    analysis_ids: Iterable[Any],
    cluster_by_analysis_id: Mapping[str, int],
) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Open the normal XY workspace with a temporary analysis-id keyed cluster overlay.

    Cluster labels are presentation/analysis context only. They do not write a source
    column, Work Group or Generation unless the user explicitly saves them later.
    """
    ids = [str(value).strip() for value in analysis_ids if str(value).strip()]
    overlay = {
        analysis_id: cluster_label(int(cluster_by_analysis_id[analysis_id]))
        for analysis_id in ids
        if analysis_id in cluster_by_analysis_id
    }
    cluster_count = len({value for value in overlay.values() if value != "Шум / −1"})
    return seed_plot_handoff(
        state,
        dataset_ids=dataset_ids,
        analysis_ids=ids,
        context={
            "origin": "Кластеризация",
            "label": f"Кластеры · {len(ids)} точек",
            "overlay_columns": {CLUSTER_OVERLAY_COLUMN: overlay},
            "preferred_group": CLUSTER_OVERLAY_COLUMN,
        },
        notice=(
            f"На XY передано {len(ids)} точек · {cluster_count} кластеров. "
            "Cluster — временная группировка; исходные данные и Generation не изменены."
        ),
    )
