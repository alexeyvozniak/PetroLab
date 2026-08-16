from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, MutableMapping

from petrolab.ui.table_filters import normalize_filter_mode


@dataclass(slots=True)
class TableViewState:
    query: str = ""
    column_mode: str = "Основное"
    custom_fields: list[str] = field(default_factory=list)
    filter_column: str = "Без фильтра"
    filter_mode: str = "Оставить"
    filter_values: list[str] = field(default_factory=list)
    filter_min: float | None = None
    filter_max: float | None = None
    group_column: str = "Не группировать"
    advanced_group_column: str = ""
    sort_column: str = "Без сортировки"
    sort_direction: str = "По возрастанию"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "TableViewState":
        data = dict(payload or {})
        allowed = set(cls.__dataclass_fields__)
        clean = {key: value for key, value in data.items() if key in allowed}
        clean["custom_fields"] = [str(item) for item in clean.get("custom_fields", []) or []]
        clean["filter_values"] = [str(item) for item in clean.get("filter_values", []) or []]
        clean["filter_mode"] = normalize_filter_mode(clean.get("filter_mode", "Оставить"))
        for key in ("filter_min", "filter_max"):
            value = clean.get(key)
            if value in (None, ""):
                clean[key] = None
            else:
                try:
                    clean[key] = float(value)
                except (TypeError, ValueError):
                    clean[key] = None
        return cls(**clean)


def _get(mapping: MutableMapping[str, Any], key: str, default: Any = None) -> Any:
    try:
        return mapping.get(key, default)
    except AttributeError:
        return mapping[key] if key in mapping else default


def capture_table_view(mapping: MutableMapping[str, Any], key_prefix: str) -> TableViewState:
    filter_column = str(_get(mapping, f"{key_prefix}_filter_column", "Без фильтра"))
    state = TableViewState(
        query=str(_get(mapping, f"{key_prefix}_query", "") or ""),
        column_mode=str(_get(mapping, f"{key_prefix}_column_mode", "Основное")),
        custom_fields=[str(item) for item in (_get(mapping, f"{key_prefix}_custom_fields", []) or [])],
        filter_column=filter_column,
        filter_mode=normalize_filter_mode(_get(mapping, f"{key_prefix}_filter_mode_{filter_column}", "Оставить")),
        group_column=str(_get(mapping, f"{key_prefix}_group_col", "Не группировать")),
        advanced_group_column=str(_get(mapping, f"{key_prefix}_advanced_group_col", "") or ""),
        sort_column=str(_get(mapping, f"{key_prefix}_sort_column", "Без сортировки")),
        sort_direction=str(_get(mapping, f"{key_prefix}_sort_direction", "По возрастанию")),
    )
    if filter_column != "Без фильтра":
        values = _get(mapping, f"{key_prefix}_filter_values_{filter_column}", []) or []
        state.filter_values = [str(item) for item in values]
        for field_name, suffix in (("filter_min", "min"), ("filter_max", "max")):
            value = _get(mapping, f"{key_prefix}_filter_{suffix}_{filter_column}", None)
            if value not in (None, ""):
                try:
                    setattr(state, field_name, float(value))
                except (TypeError, ValueError):
                    pass
    return state


def apply_table_view(
    mapping: MutableMapping[str, Any],
    key_prefix: str,
    state: TableViewState,
) -> None:
    mapping[f"{key_prefix}_query"] = state.query
    mapping[f"{key_prefix}_column_mode"] = state.column_mode
    mapping[f"{key_prefix}_custom_fields"] = list(state.custom_fields)
    mapping[f"{key_prefix}_filter_column"] = state.filter_column
    mapping[f"{key_prefix}_group_col"] = state.group_column
    mapping[f"{key_prefix}_advanced_group_col"] = state.advanced_group_column
    mapping[f"{key_prefix}_sort_column"] = state.sort_column
    mapping[f"{key_prefix}_sort_direction"] = state.sort_direction

    if state.filter_column != "Без фильтра":
        mapping[f"{key_prefix}_filter_mode_{state.filter_column}"] = normalize_filter_mode(state.filter_mode)
        mapping[f"{key_prefix}_filter_values_{state.filter_column}"] = list(state.filter_values)
        if state.filter_min is not None:
            mapping[f"{key_prefix}_filter_min_{state.filter_column}"] = float(state.filter_min)
        if state.filter_max is not None:
            mapping[f"{key_prefix}_filter_max_{state.filter_column}"] = float(state.filter_max)


def clear_table_view(mapping: MutableMapping[str, Any], key_prefix: str) -> None:
    previous_filter = str(_get(mapping, f"{key_prefix}_filter_column", "Без фильтра"))
    keys = [
        f"{key_prefix}_query",
        f"{key_prefix}_column_mode",
        f"{key_prefix}_custom_fields",
        f"{key_prefix}_filter_column",
        f"{key_prefix}_group_col",
        f"{key_prefix}_advanced_group_col",
        f"{key_prefix}_sort_column",
        f"{key_prefix}_sort_direction",
    ]
    if previous_filter != "Без фильтра":
        keys.extend(
            [
                f"{key_prefix}_filter_mode_{previous_filter}",
                f"{key_prefix}_filter_values_{previous_filter}",
                f"{key_prefix}_filter_min_{previous_filter}",
                f"{key_prefix}_filter_max_{previous_filter}",
            ]
        )
    for key in keys:
        mapping.pop(key, None)
