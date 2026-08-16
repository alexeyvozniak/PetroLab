from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping, MutableMapping, Sequence

from petrolab.smart_start import PlotRecommendation, recommendations
from petrolab.ui.plot_spec import PlotSpec


_PLOT_SCOPE_PROJECT_KEY = "_petrolab_plot_scope_project_id"
_PLOT_SCOPE_DATASETS_KEY = "_petrolab_plot_scope_dataset_ids"
_PLOT_SCOPE_ANALYSES_KEY = "_petrolab_plot_scope_analysis_ids"
_PLOT_SCOPE_CONTEXT_KEY = "_petrolab_plot_scope_context"
_PLOT_SCOPE_LABEL_KEY = "_petrolab_plot_scope_label"


@dataclass(frozen=True)
class ResolvedPlotScope:
    dataset_ids: tuple[int, ...]
    analysis_ids: tuple[str, ...]
    context: dict[str, Any]
    context_label: str = ""
    explicit: bool = False


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


def _route_is_explicit(
    requested_dataset_ids: Iterable[Any],
    requested_analysis_ids: Iterable[Any],
    requested_context: Mapping[str, Any] | None,
) -> bool:
    return bool(
        _unique_ints(requested_dataset_ids)
        or _unique_strings(requested_analysis_ids)
        or requested_context is not None
    )


def resolve_plot_scope(
    *,
    available_dataset_ids: Iterable[int],
    work_context: Mapping[str, Any] | None = None,
    requested_dataset_ids: Iterable[Any] = (),
    requested_analysis_ids: Iterable[Any] = (),
    requested_context: Mapping[str, Any] | None = None,
) -> ResolvedPlotScope:
    """Resolve the normal XY scope without silently mixing two scientific scopes.

    An explicit route handoff is authoritative and never inherits analysis IDs from
    a previous WorkContext. This matters after import/search/Selection: combining a
    new dataset scope with stale point IDs can empty or distort a graph just as badly
    as broadening a point Selection to an entire dataset.
    """
    available = _unique_ints(available_dataset_ids)
    available_set = set(available)
    explicit = _route_is_explicit(
        requested_dataset_ids,
        requested_analysis_ids,
        requested_context,
    )

    if explicit:
        requested_datasets = _unique_ints(requested_dataset_ids)
        chosen = requested_datasets if requested_datasets else available
        analyses = _unique_strings(requested_analysis_ids)
        context = dict(requested_context or {})
        label = str(context.get("label") or context.get("scope") or "").strip()
    else:
        context = dict(work_context or {})
        context_datasets = _unique_ints(context.get("dataset_ids", ()))
        chosen = context_datasets or available
        analyses = _unique_strings(context.get("analysis_ids", ()))
        label = str(context.get("label") or "").strip()

    chosen = tuple(value for value in chosen if value in available_set)
    return ResolvedPlotScope(
        dataset_ids=chosen,
        analysis_ids=analyses,
        context=context,
        context_label=label,
        explicit=explicit,
    )


def _clear_persisted_plot_scope(state: MutableMapping[str, Any]) -> None:
    for key in (
        _PLOT_SCOPE_PROJECT_KEY,
        _PLOT_SCOPE_DATASETS_KEY,
        _PLOT_SCOPE_ANALYSES_KEY,
        _PLOT_SCOPE_CONTEXT_KEY,
        _PLOT_SCOPE_LABEL_KEY,
    ):
        state.pop(key, None)


def consume_plot_scope(
    state: MutableMapping[str, Any],
    *,
    project_id: int,
    available_dataset_ids: Iterable[int],
    work_context: Mapping[str, Any] | None = None,
) -> ResolvedPlotScope:
    """Consume a route handoff once, then keep that graph scope stable across reruns.

    Streamlit reruns after every widget interaction. A transient ``pop``-only handoff
    therefore shows the right point Selection once and can broaden on the very next
    click. This function persists the resolved graph membership separately from the
    global WorkContext until another explicit plot handoff or project change occurs.
    """
    stored_project = state.get(_PLOT_SCOPE_PROJECT_KEY)
    try:
        same_project = stored_project is not None and int(stored_project) == int(project_id)
    except (TypeError, ValueError):
        same_project = False
    if stored_project is not None and not same_project:
        _clear_persisted_plot_scope(state)

    sentinel = object()
    incoming_datasets = state.pop("workflow_plot_dataset_ids", sentinel)
    incoming_analyses = state.pop("workflow_plot_analysis_ids", sentinel)
    incoming_context = state.pop("workflow_plot_context", sentinel)
    incoming = any(value is not sentinel for value in (incoming_datasets, incoming_analyses, incoming_context))

    if incoming:
        scope = resolve_plot_scope(
            available_dataset_ids=available_dataset_ids,
            requested_dataset_ids=() if incoming_datasets is sentinel else incoming_datasets,
            requested_analysis_ids=() if incoming_analyses is sentinel else incoming_analyses,
            requested_context=None if incoming_context is sentinel else incoming_context,
        )
        state[_PLOT_SCOPE_PROJECT_KEY] = int(project_id)
        state[_PLOT_SCOPE_DATASETS_KEY] = list(scope.dataset_ids)
        state[_PLOT_SCOPE_ANALYSES_KEY] = list(scope.analysis_ids)
        state[_PLOT_SCOPE_CONTEXT_KEY] = dict(scope.context)
        state[_PLOT_SCOPE_LABEL_KEY] = scope.context_label
        return scope

    if state.get(_PLOT_SCOPE_PROJECT_KEY) is not None:
        stored_context = state.get(_PLOT_SCOPE_CONTEXT_KEY)
        scope = resolve_plot_scope(
            available_dataset_ids=available_dataset_ids,
            requested_dataset_ids=state.get(_PLOT_SCOPE_DATASETS_KEY, ()),
            requested_analysis_ids=state.get(_PLOT_SCOPE_ANALYSES_KEY, ()),
            requested_context=stored_context if isinstance(stored_context, Mapping) else {},
        )
        return ResolvedPlotScope(
            dataset_ids=scope.dataset_ids,
            analysis_ids=scope.analysis_ids,
            context=scope.context,
            context_label=str(state.get(_PLOT_SCOPE_LABEL_KEY) or scope.context_label),
            explicit=True,
        )

    return resolve_plot_scope(
        available_dataset_ids=available_dataset_ids,
        work_context=work_context,
    )


def clear_exact_plot_scope(state: MutableMapping[str, Any]) -> None:
    """Explicitly broaden a persisted point-level graph to its dataset-level scope."""
    state[_PLOT_SCOPE_ANALYSES_KEY] = []
    context = state.get(_PLOT_SCOPE_CONTEXT_KEY)
    if isinstance(context, dict):
        context = dict(context)
        context.pop("analysis_ids", None)
        state[_PLOT_SCOPE_CONTEXT_KEY] = context
    state.pop("workflow_plot_analysis_ids", None)


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


def seed_import_plot_handoff(
    state: MutableMapping[str, Any],
    dataset_ids: Iterable[Any],
) -> tuple[int, ...]:
    """Prepare freshly imported datasets for the normal Smart Start plot workspace."""
    datasets = _unique_ints(dataset_ids)
    for key in list(state):
        if str(key).startswith("multi_panel_") or str(key).startswith("_multi_panel_"):
            state.pop(key, None)
    state["workflow_plot_dataset_ids"] = list(datasets)
    state["workflow_plot_analysis_ids"] = []
    state["workflow_plot_context"] = {
        "origin": "import",
        "dataset_ids": list(datasets),
        "label": "Только что импортированные данные",
    }
    state["workflow_plot_notice"] = (
        "Открыты только что импортированные данные. PetroLab выбрал безопасный стартовый график; "
        "оси можно сразу изменить."
    )
    return datasets


def seed_selection_plot_handoff(
    state: MutableMapping[str, Any],
    *,
    dataset_ids: Iterable[Any],
    analysis_ids: Iterable[Any],
    origin: str = "Selection",
) -> tuple[tuple[int, ...], tuple[str, ...]]:
    """Open exactly the selected analyses in the normal XY workspace."""
    datasets = _unique_ints(dataset_ids)
    analyses = _unique_strings(analysis_ids)
    state["workflow_plot_dataset_ids"] = list(datasets)
    state["workflow_plot_analysis_ids"] = list(analyses)
    state["workflow_plot_context"] = {
        "origin": str(origin or "Selection"),
        "dataset_ids": list(datasets),
        "analysis_ids": list(analyses),
        "label": f"Selection · {len(analyses)} точек",
    }
    state["workflow_plot_notice"] = f"В график передан точный отбор: {len(analyses)} точек."
    return datasets, analyses


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
