from __future__ import annotations

from typing import Mapping

import pandas as pd

SUPPORTED_MEASUREMENT_OVERRIDES = {
    "FeO": ("FeO", "FeOt"),
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


def _duplicate_scientific_inputs(
    columns: list[str] | tuple[str, ...] | pd.Index,
    column_map: Mapping[str, object] | None,
) -> tuple[str, ...]:
    mapping = column_map if isinstance(column_map, Mapping) else {}
    conflicts: list[str] = []
    for column in columns:
        name = str(column)
        if "__" not in name:
            continue
        base, suffix = name.rsplit("__", 1)
        if not suffix.isdigit():
            continue
        info = mapping.get(name, {})
        kind = info.get("quantity_kind") if isinstance(info, Mapping) else None
        if kind in {"oxide", "trace_element", "element_concentration"}:
            conflicts.append(f"{base} / {name}")
    return tuple(sorted(conflicts))


def validate_measurement_overrides(
    columns: list[str] | tuple[str, ...] | pd.Index,
    overrides: Mapping[str, str] | None,
) -> dict[str, str]:
    available = {str(column) for column in columns}
    requested = dict(overrides or {})

    # Fe2O3 is too ambiguous to accept silently: it can mean measured ferric iron or
    # total Fe reported on an Fe2O3 basis. User-facing import also asks explicitly for
    # FeO vs FeOt; FeO remains backward-compatible here for legacy/programmatic callers.
    if "Fe2O3" in available and "Fe2O3" not in requested:
        raise ValueError(
            "Для колонки Fe2O3 нужно явно подтвердить смысл: отдельно заданное Fe3+ "
            "или total Fe, выраженное как Fe2O3t."
        )

    clean: dict[str, str] = {}
    for source, target in requested.items():
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

    Iron reporting choices are stored with the dataset and never inferred from numeric
    values. Duplicate canonical scientific inputs are blocked rather than selected by
    physical Excel-column order.
    """
    duplicates = _duplicate_scientific_inputs(dataframe.columns, column_map)
    if duplicates:
        raise ValueError(
            "После нормализации обнаружены конфликтующие научные колонки: "
            + ", ".join(duplicates)
            + ". Оставьте или выберите один исходный столбец для каждого компонента."
        )

    clean = validate_measurement_overrides(dataframe.columns, overrides)
    out = dataframe.copy()
    mapped = _copy_column_map(column_map)

    for source, target in clean.items():
        if source == target:
            continue
        out = out.rename(columns={source: target})
        info = dict(mapped.pop(source, {}))
        info["normalized_from_semantics"] = source
        if target == "FeOt":
            info["warning"] = "total Fe expressed as FeO; not a measured FeO/Fe2+ value"
        elif target == "Fe2O3t":
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
