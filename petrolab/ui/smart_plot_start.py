from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from petrolab.smart_start import PlotRecommendation, recommendations
from petrolab.ui.plot_spec import PlotSpec


@dataclass(frozen=True)
class ResolvedPlotScope:
    dataset_ids: tuple[int, ...]
    analysis_ids: tuple[str, ...]
    context: dict[str, Any]
    context_label: str = ""


def _unique_ints(values: Iterable[Any]) -> tuple[int, ...]:
    result: list[int] = []
    for value in values:
        try:
            item = int(value)
        except (TypeError, ValueError):
            continue
        if item not in result:
            result.append(item)
    return tuple(result)


def _unique_strings(values: Iterable[Any]) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if item and item not in result:
            result.append(item)
    return tuple(result)


def resolve_plot_scope(
    *,
    available_dataset_ids: Iterable[int],
    work_context: Mapping[str, Any] | None = None,
    requested_dataset_ids: Iterable[Any] = (),
    requested_analysis_ids: Iterable[Any] = (),
    requested_context: Mapping[str, Any] | None = None,
) -> ResolvedPlotScope:
    """Resolve the normal XY scope without asking again for context PetroLab already knows.

    Explicit route handoff wins over the persistent WorkContext. Every dataset id is
    intersected with the currently accessible project scope so stale/deleted ids can
    never broaden or break the graph implicitly.
    """
    available = _unique_ints(available_dataset_ids)
    available_set = set(available)
    explicit_datasets = _unique_ints(requested_dataset_ids)
    context = dict(requested_context or work_context or {})
    context_datasets = _unique_ints((work_context or {}).get("dataset_ids", ()))

    chosen = explicit_datasets or context_datasets or available
    chosen = tuple(value for value in chosen if value in available_set)

    explicit_analyses = _unique_strings(requested_analysis_ids)
    context_analyses = _unique_strings((work_context or {}).get("analysis_ids", ()))
    analyses = explicit_analyses or context_analyses

    return ResolvedPlotScope(
        dataset_ids=chosen,
        analysis_ids=analyses,
        context=context,
        context_label=str((work_context or {}).get("label") or "").strip(),
    )


def choose_xy_recommendation(
    mineral_keys: Sequence[str],
    columns: Iterable[str],
    numeric_columns: Iterable[str],
) -> PlotRecommendation | None:
    """Return one safe deterministic starting XY, never a scientific conclusion."""
    numeric = {str(value) for value in numeric_columns}
    key = str(mineral_keys[0]) if len(mineral_keys) == 1 else "generic"
    for item in recommendations(key, columns, limit=6):
        if item.route == "plots" and item.x in numeric and item.y in numeric and item.x != item.y:
            return item
    return None


def seed_xy_state(
    state: MutableMapping[str, Any],
    *,
    numeric_columns: Sequence[str],
    recommendation: PlotRecommendation | None,
    x_key: str = "quick_x",
    y_key: str = "quick_y",
) -> tuple[str, str]:
    """Seed widget state only when the current values are missing or invalid.

    Once the user has made a valid manual axis choice it is preserved. Smart Start
    is therefore an initial view, not an auto-correcting opinionated controller.
    """
    numeric = [str(value) for value in numeric_columns]
    if len(numeric) < 2:
        raise ValueError("Smart Start requires at least two numeric columns.")

    preferred_x = recommendation.x if recommendation and recommendation.x in numeric else numeric[0]
    current_x = str(state.get(x_key) or "")
    if current_x not in numeric:
        state[x_key] = preferred_x
        current_x = preferred_x

    y_options = [column for column in numeric if column != current_x]
    preferred_y = (
        recommendation.y
        if recommendation and recommendation.y in y_options
        else y_options[0]
    )
    current_y = str(state.get(y_key) or "")
    if current_y not in y_options:
        state[y_key] = preferred_y
        current_y = preferred_y
    return current_x, current_y


def advanced_recipe_from_spec(
    spec: PlotSpec,
    *,
    minerals: Iterable[str] = (),
    query: str = "",
) -> dict[str, Any]:
    """Translate the current compact graph into the legacy deep editor recipe.

    This is an adapter only. PlotSpec remains the canonical graph definition.
    """
    return {
        "dataset_ids": list(spec.dataset_ids),
        "minerals": list(_unique_strings(minerals)),
        "query": str(query or ""),
        "visible_sources": list(spec.visible_sources),
        "hidden_sources": list(spec.hidden_sources),
        "x": spec.x,
        "y": spec.y,
        "group_col": spec.group_column or None,
        "x_label": spec.x_label or spec.x,
        "y_label": spec.y_label or spec.y,
        "title": spec.title,
        "log_x": bool(spec.log_x),
        "log_y": bool(spec.log_y),
        "marker_size": float(spec.marker_size or 0.0),
        "style_map": {str(key): dict(value) for key, value in spec.style_map.items()},
    }
