from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Mapping, MutableMapping


ADVANCED_CURRENT_RECIPE_KEY = "_petrolab_current_advanced_recipe"

_COMPACT_OWNED_KEYS = {
    "dataset_ids",
    "minerals",
    "query",
    "visible_sources",
    "hidden_sources",
    "x",
    "y",
    "group_col",
    "x_label",
    "y_label",
    "title",
    "log_x",
    "log_y",
    "marker_size",
    "style_map",
    "_scientific_context",
}

_DEEP_ONLY_KEYS = {
    "column_filters",
    "outlier_filters",
    "journal_preset",
    "x_min",
    "x_max",
    "y_min",
    "y_max",
    "show_grid",
    "monochrome",
    "show_legend",
    "annotate",
    "label_col",
    "annotate_top_n",
    "figure_width",
    "figure_height",
    "font_size",
    "tick_size",
    "spine_width",
    "title_size",
}


@dataclass(frozen=True)
class AdvancedRecipeMerge:
    recipe: dict[str, Any]
    resumed_deep_state: bool = False
    dropped_incompatible_deep_state: bool = False
    deep_summary: tuple[str, ...] = ()


def _unique_ints(values: Any) -> tuple[int, ...]:
    result: list[int] = []
    if not isinstance(values, (list, tuple)):
        return ()
    for value in values:
        try:
            item = int(value)
        except (TypeError, ValueError):
            continue
        if item not in result:
            result.append(item)
    return tuple(result)


def _unique_strings(values: Any) -> tuple[str, ...]:
    result: list[str] = []
    if not isinstance(values, (list, tuple)):
        return ()
    for value in values:
        item = str(value or "").strip()
        if item and item not in result:
            result.append(item)
    return tuple(result)


def _context_fingerprint(value: Any) -> tuple[Any, ...]:
    raw = value if isinstance(value, Mapping) else {}
    return (
        _unique_ints(raw.get("dataset_ids")),
        _unique_strings(raw.get("analysis_ids")),
        str(raw.get("sample_id") or ""),
        str(raw.get("sample") or ""),
        str(raw.get("thin_section_id") or ""),
        str(raw.get("query") or ""),
        str(raw.get("origin") or ""),
    )


def current_advanced_recipe(state: Mapping[str, Any]) -> dict[str, Any]:
    raw = state.get(ADVANCED_CURRENT_RECIPE_KEY)
    return deepcopy(raw) if isinstance(raw, dict) else {}


def store_current_advanced_recipe(
    state: MutableMapping[str, Any],
    recipe: Mapping[str, Any],
) -> dict[str, Any]:
    payload = deepcopy(dict(recipe))
    state[ADVANCED_CURRENT_RECIPE_KEY] = payload
    return payload


def clear_current_advanced_recipe(state: MutableMapping[str, Any]) -> None:
    state.pop(ADVANCED_CURRENT_RECIPE_KEY, None)


def deep_state_summary(recipe: Mapping[str, Any] | None) -> tuple[str, ...]:
    raw = dict(recipe or {})
    result: list[str] = []

    column_filters = raw.get("column_filters")
    if isinstance(column_filters, dict) and any(column_filters.values()):
        result.append("категориальные фильтры")

    outlier = raw.get("outlier_filters")
    if isinstance(outlier, dict):
        active_outlier = any(
            value not in (None, "", False, [], {}, ())
            for key, value in outlier.items()
            if key not in {"mode", "method"}
        )
        if active_outlier:
            result.append("выбросы / исключённые точки")

    if any(raw.get(key) is not None for key in ("x_min", "x_max", "y_min", "y_max")):
        result.append("границы осей")

    if bool(raw.get("annotate")) or raw.get("label_col"):
        result.append("подписи точек")

    publication_keys = (
        "journal_preset",
        "monochrome",
        "show_legend",
        "figure_width",
        "figure_height",
        "font_size",
        "tick_size",
        "spine_width",
        "title_size",
    )
    if any(key in raw for key in publication_keys):
        result.append("публикационное оформление")

    return tuple(dict.fromkeys(result))


def _compatible_for_deep_resume(
    compact: Mapping[str, Any],
    parked: Mapping[str, Any],
) -> bool:
    if str(compact.get("x") or "") != str(parked.get("x") or ""):
        return False
    if str(compact.get("y") or "") != str(parked.get("y") or ""):
        return False
    if _unique_ints(compact.get("dataset_ids")) != _unique_ints(parked.get("dataset_ids")):
        return False
    compact_minerals = _unique_strings(compact.get("minerals"))
    parked_minerals = _unique_strings(parked.get("minerals"))
    if compact_minerals and parked_minerals and compact_minerals != parked_minerals:
        return False

    compact_context = compact.get("_scientific_context")
    parked_context = parked.get("_scientific_context")
    if compact_context is not None or parked_context is not None:
        if _context_fingerprint(compact_context) != _context_fingerprint(parked_context):
            return False
    return True


def advanced_recipe_for_entry(
    compact_recipe: Mapping[str, Any],
    parked_recipe: Mapping[str, Any] | None,
) -> AdvancedRecipeMerge:
    """Create the deep-editor recipe without silently reusing incompatible filters.

    Compact controls always win for state they can represent. Deep-only filters and
    publication settings are resumed only when dataset scope, mineral scope, X/Y and
    exact scientific context still match the graph they were created for. Otherwise
    they are deliberately discarded for this entry rather than being applied to a
    different scientific question.
    """
    compact = deepcopy(dict(compact_recipe))
    parked = deepcopy(dict(parked_recipe or {}))
    summary = deep_state_summary(parked)
    if not parked or not summary:
        return AdvancedRecipeMerge(recipe=compact)

    compatible = _compatible_for_deep_resume(compact, parked)
    if not compatible:
        for key in _DEEP_ONLY_KEYS:
            compact.pop(key, None)
        return AdvancedRecipeMerge(
            recipe=compact,
            dropped_incompatible_deep_state=True,
            deep_summary=summary,
        )

    merged = parked
    for key in _COMPACT_OWNED_KEYS:
        if key in compact:
            merged[key] = deepcopy(compact[key])
    return AdvancedRecipeMerge(
        recipe=merged,
        resumed_deep_state=True,
        deep_summary=summary,
    )
