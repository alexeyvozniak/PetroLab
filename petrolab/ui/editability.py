from __future__ import annotations

import json
from collections.abc import Mapping, Sequence


def dataset_source_columns(dataset: Mapping[str, object]) -> set[str]:
    """Return columns that belong to the persisted source schema of one dataset.

    Display metadata, QC columns and derived values are deliberately absent from the
    stored column map. Legacy datasets with no usable map are treated as read-only: it is
    safer to require re-import than to invent a source column that cannot be traced back.
    """
    raw = dataset.get("column_map_json")
    if isinstance(raw, Mapping):
        column_map = raw
    else:
        try:
            column_map = json.loads(str(raw or "{}"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return set()

    if not isinstance(column_map, Mapping):
        return set()

    return {
        str(column)
        for column, info in column_map.items()
        if str(column) != "__schema__" and isinstance(info, Mapping)
    }


def common_editable_source_columns(
    datasets: Sequence[Mapping[str, object]],
    selected_ids: Sequence[int],
) -> set[str]:
    """Return source columns safely editable across every selected dataset.

    Streamlit's data editor disables whole columns rather than individual cells. In a
    union dataframe, allowing a column that exists only in dataset A would make the empty
    cells of dataset B look writable and create a database-only pseudo-source field. The
    safe contract is therefore the intersection of physical source schemas. Users can
    narrow the selection to one dataset when they need a schema-specific column.
    """
    wanted = {int(value) for value in selected_ids}
    selected = [
        dataset
        for dataset in datasets
        if int(dataset.get("id", -1)) in wanted
    ]
    if not selected:
        return set()

    schemas = [dataset_source_columns(dataset) for dataset in selected]
    if not schemas or any(not schema for schema in schemas):
        return set()

    editable = set(schemas[0])
    for schema in schemas[1:]:
        editable.intersection_update(schema)
    return editable
