from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd


def _canonical_value(value: Any) -> Any:
    """Convert pandas/numpy scalar values into stable Python values for comparison."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str):
        return value.strip()
    if hasattr(value, "item"):
        return value.item()
    return value


def values_equal(left: Any, right: Any) -> bool:
    """Compare edited values while treating equivalent numeric scalars as equal."""
    left = _canonical_value(left)
    right = _canonical_value(right)
    if left is None and right is None:
        return True
    if isinstance(left, (int, float)) and isinstance(right, (int, float)):
        try:
            left_value = float(left)
            right_value = float(right)
            if math.isnan(left_value) and math.isnan(right_value):
                return True
            if math.isinf(left_value) or math.isinf(right_value):
                return left_value == right_value
            return abs(left_value - right_value) <= 1e-12
        except (TypeError, ValueError, OverflowError):
            return False
    return left == right


def compute_changes(
    original: pd.DataFrame,
    edited: pd.DataFrame,
    protected_columns: Iterable[str] = (),
) -> list[dict[str, Any]]:
    """Return cell-level changes keyed by immutable PetroLab analysis IDs."""
    if "_analysis_id" not in original.columns or "_analysis_id" not in edited.columns:
        return []

    old_map = original.set_index("_analysis_id", drop=False)
    new_map = edited.set_index("_analysis_id", drop=False)
    protected = set(protected_columns)
    common_columns = [
        column
        for column in original.columns
        if column in edited.columns
        and column not in protected
        and not str(column).startswith("_")
    ]

    changes: list[dict[str, Any]] = []
    for analysis_id in new_map.index.intersection(old_map.index):
        old_row = old_map.loc[analysis_id]
        new_row = new_map.loc[analysis_id]
        for column in common_columns:
            old_value = _canonical_value(old_row[column])
            new_value = _canonical_value(new_row[column])
            if values_equal(old_value, new_value):
                continue
            source_row = old_row.get("_source_row")
            changes.append(
                {
                    "analysis_id": str(analysis_id),
                    "dataset_id": int(old_row["_dataset_id"]),
                    "source_row": None if pd.isna(source_row) else int(source_row),
                    "column_name": column,
                    "old_value": old_value,
                    "new_value": new_value,
                }
            )
    return changes


def apply_quick_filter(dataframe: pd.DataFrame, query: str) -> pd.DataFrame:
    """Filter rows when any displayed value contains the literal case-insensitive query."""
    if dataframe.empty or not query.strip():
        return dataframe
    needle = query.strip()
    mask = dataframe.astype("string").apply(
        lambda column: column.str.contains(
            needle,
            case=False,
            na=False,
            regex=False,
        )
    ).any(axis=1)
    return dataframe.loc[mask]


def apply_column_filters(
    dataframe: pd.DataFrame,
    chosen_filters: Mapping[str, list[str]],
) -> pd.DataFrame:
    """Apply exact-value filters to selected dataframe columns."""
    result = dataframe
    for column, values in chosen_filters.items():
        if not values or column not in result.columns:
            continue
        selected = {str(value) for value in values}
        result = result[result[column].astype(str).isin(selected)]
    return result


def dataset_label(dataset: Mapping[str, Any]) -> str:
    """Build a stable human-readable dataset selector label.

    Dataset names, row counts, and source filenames are not unique. Including the
    immutable database ID prevents two otherwise identical labels from collapsing
    when UI code uses labels as dictionary keys.
    """
    suffix = f' · ID {int(dataset["id"])}' if dataset.get("id") is not None else ""
    return (
        f'{dataset["project_name"]} · {dataset["name"]} · '
        f'{dataset["row_count"]} строк · {dataset["source_filename"]}{suffix}'
    )


def row_identity(row: pd.Series) -> str:
    """Build a compact point identity from common sample/grain/point columns."""
    preferred_fragments = (
        "sample",
        "образ",
        "grain",
        "зерн",
        "point",
        "точк",
        "spot",
        "analysis",
        "name",
        "group",
        "тип",
    )
    pieces: list[str] = []
    for fragment in preferred_fragments:
        for column in row.index:
            if str(column).startswith("_"):
                continue
            value = row[column]
            if fragment in str(column).lower() and pd.notna(value):
                text = f"{column}: {value}"
                if text not in pieces:
                    pieces.append(text)
                if len(pieces) >= 4:
                    break
        if len(pieces) >= 4:
            break

    if pieces:
        return " · ".join(pieces)

    source_row = row.get("_source_row")
    if pd.notna(source_row):
        return f"Строка {int(source_row)}"
    return f"Строка {row.name}"


def display_value(value: Any) -> str:
    """Render mixed pandas scalars safely in UI property tables."""
    canonical = _canonical_value(value)
    return "" if canonical is None else str(canonical)
