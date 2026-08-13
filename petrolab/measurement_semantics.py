from __future__ import annotations

from typing import Mapping

import pandas as pd

SUPPORTED_MEASUREMENT_OVERRIDES = {
    "Fe2O3": ("Fe2O3", "Fe2O3t"),
}


def validate_measurement_overrides(
    columns: list[str] | tuple[str, ...] | pd.Index,
    overrides: Mapping[str, str] | None,
) -> dict[str, str]:
    available = {str(column) for column in columns}
    requested = dict(overrides or {})

    # A bare historical Fe2O3 header is scientifically ambiguous in the import layer:
    # it may mean measured ferric iron or total Fe reported on an Fe2O3 basis. Do not
    # silently default to either interpretation merely because a UI widget has a first
    # option or because the caller omitted the mapping.
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

    A bare Fe2O3 header is inherently ambiguous in historical laboratory tables: it can
    mean separately supplied ferric iron or total Fe reported on an Fe2O3 basis. The
    choice is stored with the dataset and never inferred from the numbers themselves.
    """
    clean = validate_measurement_overrides(dataframe.columns, overrides)
    out = dataframe.copy()
    mapped = dict(column_map)

    for source, target in clean.items():
        if source == target:
            continue
        out = out.rename(columns={source: target})
        info = dict(mapped.pop(source, {}))
        info["normalized_from_semantics"] = source
        info["warning"] = "total Fe expressed as Fe2O3; not measured ferric Fe"
        mapped[target] = info

    mapped.setdefault("__schema__", {})["measurement"] = clean
    return out, mapped, clean


def stored_measurement_overrides(column_map: Mapping[str, object]) -> dict[str, str]:
    schema = column_map.get("__schema__", {}) if isinstance(column_map, Mapping) else {}
    if not isinstance(schema, Mapping):
        return {}
    measurement = schema.get("measurement", {})
    return dict(measurement) if isinstance(measurement, Mapping) else {}
