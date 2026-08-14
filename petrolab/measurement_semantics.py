from __future__ import annotations

from typing import Mapping

import pandas as pd

SUPPORTED_MEASUREMENT_OVERRIDES = {
    "Fe2O3": ("Fe2O3", "Fe2O3t"),
}


def _copy_column_map(column_map: Mapping[str, object]) -> dict[str, dict]:
    """Copy provenance metadata without sharing the nested __schema__ mapping."""
    mapped: dict[str, dict] = {}
    for key, value in column_map.items():
        if isinstance(value, Mapping):
            mapped[str(key)] = dict(value)
        else:
            mapped[str(key)] = {}
    schema = column_map.get("__schema__", {})
    mapped["__schema__"] = dict(schema) if isinstance(schema, Mapping) else {}
    return mapped


def validate_measurement_overrides(
    columns: list[str] | tuple[str, ...] | pd.Index,
    overrides: Mapping[str, str] | None,
) -> dict[str, str]:
    available = {str(column) for column in columns}
    clean: dict[str, str] = {}
    for source, target in (overrides or {}).items():
        source = str(source)
        target = str(target)
        allowed = SUPPORTED_MEASUREMENT_OVERRIDES.get(source)
        if allowed is None or target not in allowed:
            raise ValueError(f"Неподдерживаемая интерпретация {source} → {target}")
        if source not in available:
            raise ValueError(f"Колонка {source} отсутствует на листе")
        if target != source and target in available:
            raise ValueError(
                f"Нельзя переименовать {source} в {target}: такая колонка уже есть на листе"
            )
        clean[source] = target
    return clean


def apply_measurement_overrides(
    dataframe: pd.DataFrame,
    column_map: dict[str, dict],
    overrides: Mapping[str, str] | None,
) -> tuple[pd.DataFrame, dict[str, dict], dict[str, str]]:
    """Apply user-confirmed reporting semantics after header normalization.

    A bare Fe2O3 header is inherently ambiguous in historical laboratory tables: it can
    mean separately supplied ferric iron or total Fe reported on an Fe2O3 basis. The
    choice is stored with the dataset and never inferred from the numbers themselves.
    """
    clean = validate_measurement_overrides(dataframe.columns, overrides)
    out = dataframe.copy()
    mapped = _copy_column_map(column_map)

    for source, target in clean.items():
        if source == target:
            continue
        out = out.rename(columns={source: target})
        info = dict(mapped.pop(source, {}))
        info["normalized_from_semantics"] = source
        info["warning"] = "total Fe expressed as Fe2O3; not measured ferric Fe"
        mapped[target] = info

    mapped["__schema__"]["measurement"] = clean
    return out, mapped, clean


def stored_measurement_overrides(column_map: Mapping[str, object]) -> dict[str, str]:
    schema = column_map.get("__schema__", {}) if isinstance(column_map, Mapping) else {}
    if not isinstance(schema, Mapping):
        return {}
    measurement = schema.get("measurement", {})
    return dict(measurement) if isinstance(measurement, Mapping) else {}
