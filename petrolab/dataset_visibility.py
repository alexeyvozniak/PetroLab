from __future__ import annotations

from collections.abc import Iterable, Mapping


RESOLVED_MIXED_SUFFIX = " · Исходный mixed (разобрано)"


def is_resolved_mixed_container(dataset: Mapping[str, object]) -> bool:
    """Whether a dataset is an empty provenance container left after full phase split.

    The record must stay in PetroLab for provenance and audit. It should not compete
    with real working datasets in ordinary selectors once all analysis rows have been
    moved into mineral/phase children.
    """
    name = str(dataset.get("name") or "")
    try:
        row_count = int(dataset.get("row_count") or 0)
    except (TypeError, ValueError):
        row_count = 0
    return row_count == 0 and name.endswith(RESOLVED_MIXED_SUFFIX)


def visible_working_datasets(datasets: Iterable[Mapping[str, object]]) -> list[dict]:
    """Return normal user-facing datasets while preserving technical parents in DB."""
    return [dict(dataset) for dataset in datasets if not is_resolved_mixed_container(dataset)]
