from __future__ import annotations

from petrolab.db import list_accessible_datasets


_RESOLVED_MIXED_MARKER = "Исходный mixed (разобрано)"


def is_provenance_container(dataset: dict) -> bool:
    """Whether a dataset is a zero-row technical source retained only for provenance."""
    name = str(dataset.get("name") or "")
    try:
        row_count = int(dataset.get("row_count") or 0)
    except (TypeError, ValueError):
        row_count = 0
    purpose = str(dataset.get("membership_purpose") or "").strip().casefold()
    return purpose == "provenance" or (row_count == 0 and _RESOLVED_MIXED_MARKER.casefold() in name.casefold())


def list_working_datasets(project_id: int, *, include_provenance: bool = False) -> list[dict]:
    datasets = list_accessible_datasets(int(project_id))
    if include_provenance:
        return datasets
    return [dataset for dataset in datasets if not is_provenance_container(dataset)]
