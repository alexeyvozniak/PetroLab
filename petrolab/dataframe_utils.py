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


def _dataset_import_label(dataset: Mapping[str, Any]) -> str:
    raw = dataset.get("imported_at")
    if raw in (None, ""):
        return ""
    try:
        stamp = pd.to_datetime(raw, errors="raise")
        return stamp.strftime("%d.%m.%Y %H:%M:%S")
    except (TypeError, ValueError, OverflowError):
        return str(raw).strip()


def dataset_label(dataset: Mapping[str, Any]) -> str:
    """Build a human-readable selector label from scientific provenance, never DB IDs."""
    parts = [
        str(dataset.get("project_name") or "").strip(),
        str(dataset.get("name") or "").strip(),
    ]
    mineral = str(dataset.get("mineral_key") or "").strip()
    if mineral and mineral != "generic":
        parts.append(mineral)
    row_count = dataset.get("row_count")
    if row_count is not None:
        parts.append(f"{int(row_count)} строк")
    source = str(dataset.get("source_filename") or "").strip()
    sheet = str(dataset.get("source_sheet") or "").strip()
    if source and sheet:
        parts.append(f"{source} / {sheet}")
    elif source or sheet:
        parts.append(source or sheet)
    imported = _dataset_import_label(dataset)
    if imported:
        parts.append(f"импорт {imported}")
    return " · ".join(part for part in parts if part)


def _first_value(row: pd.Series, names: tuple[str, ...]) -> str:
    lower = {str(column).casefold(): column for column in row.index}
    for name in names:
        exact = lower.get(name.casefold())
        if exact is not None:
            value = _canonical_value(row.get(exact))
            if value not in (None, ""):
                return str(value)
    for column in row.index:
        text = str(column).casefold()
        if str(column).startswith("_"):
            continue
        if any(name.casefold() in text for name in names):
            value = _canonical_value(row.get(column))
            if value not in (None, ""):
                return str(value)
    return ""


def human_point_label(row: pd.Series, *, include_generation: bool = True) -> str:
    """Return a compact scientific point label; never expose ``_analysis_id``."""
    sample = _first_value(row, ("Sample", "Образец"))
    grain = _first_value(row, ("Grain", "Зерно"))
    point = _first_value(row, ("Point", "Spot", "Точка"))
    generation = _first_value(row, ("PetroLab Generation", "Generation", "Поколение")) if include_generation else ""

    parts: list[str] = []
    if sample:
        parts.append(sample)
    if grain:
        parts.append(f"зерно {grain}")
    if point:
        parts.append(f"точка {point}")
    if generation:
        parts.append(generation)
    if parts:
        return " · ".join(parts)

    source = _first_value(row, ("Источник", "Source", "Набор", "Dataset"))
    source_row = row.get("_source_row")
    if source and pd.notna(source_row):
        return f"{source} · строка {int(source_row)}"
    if source:
        return source
    if pd.notna(source_row):
        return f"Строка {int(source_row)}"
    return f"Строка {row.name}"


def row_identity(row: pd.Series) -> str:
    """Backward-compatible alias for the canonical human point label."""
    return human_point_label(row)


def display_value(value: Any) -> str:
    """Render mixed pandas scalars safely in UI property tables."""
    canonical = _canonical_value(value)
    return "" if canonical is None else str(canonical)
