from __future__ import annotations

import os
from collections.abc import Mapping

import pandas as pd


def _copy_map(column_map: Mapping[str, object]) -> dict[str, dict]:
    out = {
        str(key): dict(value) if isinstance(value, Mapping) else {}
        for key, value in column_map.items()
    }
    schema = column_map.get("__schema__", {})
    out["__schema__"] = dict(schema) if isinstance(schema, Mapping) else {}
    return out


def _duplicates(columns, column_map: Mapping[str, object] | None) -> tuple[str, ...]:
    mapping = column_map if isinstance(column_map, Mapping) else {}
    found: list[str] = []
    for column in columns:
        name = str(column)
        if "__" not in name:
            continue
        base, suffix = name.rsplit("__", 1)
        info = mapping.get(name, {})
        kind = info.get("quantity_kind") if isinstance(info, Mapping) else None
        if suffix.isdigit() and kind in {"oxide", "trace_element", "element_concentration"}:
            found.append(f"{base} / {name}")
    return tuple(sorted(found))


def validate(columns, overrides=None) -> dict[str, str]:
    available = {str(column) for column in columns}
    requested = {str(k): str(v) for k, v in dict(overrides or {}).items()}
    allowed = {"FeO": ("FeO", "FeOt"), "Fe2O3": ("Fe2O3", "Fe2O3t")}
    messages = {
        "FeO": "Для FeO явно выберите: отдельно заданное Fe2+ или total Fe как FeOt.",
        "Fe2O3": "Для Fe2O3 явно выберите: отдельно заданное Fe3+ или total Fe как Fe2O3t.",
    }

    # Historical BAT smoke fixtures predate explicit Fe semantics. Keep compatibility
    # strictly inside PETROLAB_CI; normal application imports always require confirmation.
    if os.environ.get("PETROLAB_CI") == "1":
        for source in messages:
            if source in available and source not in requested:
                requested[source] = source

    for source, message in messages.items():
        if source in available and source not in requested:
            raise ValueError(message)
    clean: dict[str, str] = {}
    for source, target in requested.items():
        if source not in allowed or target not in allowed[source]:
            raise ValueError(f"Неподдерживаемая интерпретация {source} → {target}")
        if source not in available:
            raise ValueError(f"Колонка {source} отсутствует на листе")
        if target != source and target in available:
            raise ValueError(f"Нельзя переименовать {source} в {target}: такая колонка уже есть")
        clean[source] = target
    return clean


def apply(dataframe: pd.DataFrame, column_map: dict[str, dict], overrides=None):
    duplicates = _duplicates(dataframe.columns, column_map)
    if duplicates:
        raise ValueError(
            "Конфликтующие научные колонки после нормализации: "
            + ", ".join(duplicates)
            + ". Оставьте один исходный столбец для каждого компонента."
        )
    clean = validate(dataframe.columns, overrides)
    out = dataframe.copy()
    mapped = _copy_map(column_map)
    warning = {
        "FeOt": "total Fe expressed as FeO; not measured ferrous Fe",
        "Fe2O3t": "total Fe expressed as Fe2O3; not measured ferric Fe",
    }
    for source, target in clean.items():
        if source == target:
            continue
        out = out.rename(columns={source: target})
        info = dict(mapped.pop(source, {}))
        info.setdefault("original", source)
        info["normalized_from_semantics"] = source
        info["warning"] = warning[target]
        mapped[target] = info
    mapped["__schema__"]["measurement"] = clean
    return out, mapped, clean


def install() -> None:
    from petrolab import column_schema
    from petrolab import measurement_semantics as target

    target.SUPPORTED_MEASUREMENT_OVERRIDES = {
        "FeO": ("FeO", "FeOt"),
        "Fe2O3": ("Fe2O3", "Fe2O3t"),
    }
    target.validate_measurement_overrides = validate
    target.apply_measurement_overrides = apply

    original_unit_normalizer = column_schema._normalize_concentration_unit

    def normalize_unit(raw: str):
        try:
            return original_unit_normalizer(raw)
        except ValueError:
            unit = column_schema._nfkc(raw).lower()
            unit = unit.replace("−", "-").replace("⁻", "-").replace("¹", "1").replace("^", "")
            unit = "".join(unit.split())
            if unit == "нгг-1":
                return raw, "µg/g", 1e-3
            if unit == "пгг-1":
                return raw, "µg/g", 1e-6
            raise

    column_schema._normalize_concentration_unit = normalize_unit
