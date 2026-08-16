from __future__ import annotations

from copy import deepcopy
from typing import Any, MutableMapping


HISTORY_KEY = "_petrolab_nav_history"
MAX_HISTORY = 20
_CONTEXT_KEYS = (
    "_petrolab_work_context",
    "workflow_plot_dataset_ids",
    "workflow_plot_analysis_ids",
    "statistics_scope",
    "statistics_datasets",
    "loaded_recipe",
)


def _snapshot(state: MutableMapping[str, Any], route: str) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key in _CONTEXT_KEYS:
        if key in state:
            values[key] = deepcopy(state[key])
    return {"route": str(route), "state": values}


def _history(state: MutableMapping[str, Any]) -> list[dict[str, Any]]:
    raw = state.get(HISTORY_KEY)
    if not isinstance(raw, list):
        raw = []
        state[HISTORY_KEY] = raw
    return raw


def push_current(state: MutableMapping[str, Any], *, current_route: str) -> None:
    history = _history(state)
    entry = _snapshot(state, current_route)
    if history and history[-1] == entry:
        return
    history.append(entry)
    if len(history) > MAX_HISTORY:
        del history[:-MAX_HISTORY]


def can_go_back(state: MutableMapping[str, Any]) -> bool:
    return bool(_history(state))


def go_back(
    state: MutableMapping[str, Any],
    *,
    current_route: str,
    valid_routes: set[str] | frozenset[str],
) -> str | None:
    history = _history(state)
    while history:
        entry = history.pop()
        route = str(entry.get("route") or "")
        if route not in valid_routes or route == current_route:
            continue
        restored = entry.get("state")
        if isinstance(restored, dict):
            for key in _CONTEXT_KEYS:
                if key in restored:
                    state[key] = deepcopy(restored[key])
                else:
                    state.pop(key, None)
        state["nav_route"] = route
        return route
    return None


def clear_history(state: MutableMapping[str, Any]) -> None:
    state.pop(HISTORY_KEY, None)
