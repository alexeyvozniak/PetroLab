from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, MutableMapping


SELECTION_KEY = "_petrolab_selection_context"
ROW_STATES_KEY = "_petrolab_row_states"

_SELECTION_MODES = {"replace", "add", "subtract"}
_ROW_STATE_KINDS = {"hidden", "excluded", "labelled"}


@dataclass(frozen=True)
class SelectionContext:
    """Canonical transient scientific selection shared by all PetroLab views.

    Selection is intentionally distinct from filtering, display row states,
    Work Group and Generation. Only immutable ``analysis_id`` values cross views.
    """

    analysis_ids: tuple[str, ...] = ()
    origin: str = ""
    label: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.analysis_ids)


@dataclass(frozen=True)
class RowStates:
    """JMP-like row states that do not change the active selection or science."""

    hidden: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    labelled: tuple[str, ...] = ()
    display_color: dict[str, str] = field(default_factory=dict)
    display_marker: dict[str, str] = field(default_factory=dict)


def _state(state: MutableMapping[str, Any] | None = None) -> MutableMapping[str, Any]:
    if state is not None:
        return state
    import streamlit as st

    return st.session_state


def _ids(values) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values or ():
        value = str(raw).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return tuple(result)


def _style_map(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        return {}
    result: dict[str, str] = {}
    for key, value in raw.items():
        analysis_id = str(key).strip()
        style = str(value).strip()
        if analysis_id and style:
            result[analysis_id] = style
    return result


def _apply_mode(current: tuple[str, ...], incoming: tuple[str, ...], mode: str) -> tuple[str, ...]:
    if mode not in _SELECTION_MODES:
        raise ValueError(f"Unknown selection mode: {mode}")
    if mode == "replace":
        return incoming
    if mode == "add":
        return _ids((*current, *incoming))
    removed = set(incoming)
    return tuple(value for value in current if value not in removed)


def read_selection(state: MutableMapping[str, Any] | None = None) -> SelectionContext:
    raw = _state(state).get(SELECTION_KEY)
    if not isinstance(raw, dict):
        return SelectionContext()
    metadata = raw.get("metadata")
    return SelectionContext(
        analysis_ids=_ids(raw.get("analysis_ids", ())),
        origin=str(raw.get("origin") or ""),
        label=str(raw.get("label") or ""),
        metadata=dict(metadata) if isinstance(metadata, dict) else {},
    )


def set_selection(
    analysis_ids,
    *,
    origin: str,
    mode: str = "replace",
    label: str = "",
    metadata: dict[str, Any] | None = None,
    state: MutableMapping[str, Any] | None = None,
) -> SelectionContext:
    store = _state(state)
    current = read_selection(store)
    combined = _apply_mode(current.analysis_ids, _ids(analysis_ids), mode)
    payload = {
        "analysis_ids": list(combined),
        "origin": str(origin or current.origin),
        "label": str(label or (current.label if mode != "replace" else "")),
        "metadata": dict(metadata if metadata is not None else (current.metadata if mode != "replace" else {})),
    }
    store[SELECTION_KEY] = payload
    return read_selection(store)


def clear_selection(state: MutableMapping[str, Any] | None = None) -> None:
    _state(state).pop(SELECTION_KEY, None)


def selection_mode_label(mode: str) -> str:
    return {
        "replace": "Заменить",
        "add": "Добавить",
        "subtract": "Вычесть",
    }.get(str(mode), "Заменить")


def read_row_states(state: MutableMapping[str, Any] | None = None) -> RowStates:
    raw = _state(state).get(ROW_STATES_KEY)
    if not isinstance(raw, dict):
        return RowStates()
    return RowStates(
        hidden=_ids(raw.get("hidden", ())),
        excluded=_ids(raw.get("excluded", ())),
        labelled=_ids(raw.get("labelled", ())),
        display_color=_style_map(raw.get("display_color")),
        display_marker=_style_map(raw.get("display_marker")),
    )


def _row_state_payload(current: RowStates) -> dict[str, Any]:
    return {
        "hidden": list(current.hidden),
        "excluded": list(current.excluded),
        "labelled": list(current.labelled),
        "display_color": dict(current.display_color),
        "display_marker": dict(current.display_marker),
    }


def set_row_state(
    kind: str,
    analysis_ids,
    *,
    mode: str = "replace",
    state: MutableMapping[str, Any] | None = None,
) -> RowStates:
    if kind not in _ROW_STATE_KINDS:
        raise ValueError(f"Unknown row-state kind: {kind}")
    store = _state(state)
    current = read_row_states(store)
    current_values = getattr(current, kind)
    updated = _apply_mode(current_values, _ids(analysis_ids), mode)
    payload = _row_state_payload(current)
    payload[kind] = list(updated)
    store[ROW_STATES_KEY] = payload
    return read_row_states(store)


def set_row_display(
    analysis_ids,
    *,
    color: str | None = None,
    marker: str | None = None,
    clear_color: bool = False,
    clear_marker: bool = False,
    state: MutableMapping[str, Any] | None = None,
) -> RowStates:
    """Apply transient display styling to exact analysis IDs.

    Styling is exploration state only. It never writes dataframe columns,
    Generation, Work Group or provenance.
    """
    store = _state(state)
    current = read_row_states(store)
    payload = _row_state_payload(current)
    ids = _ids(analysis_ids)
    colors = dict(current.display_color)
    markers = dict(current.display_marker)
    for analysis_id in ids:
        if clear_color:
            colors.pop(analysis_id, None)
        elif color is not None and str(color).strip():
            colors[analysis_id] = str(color).strip()
        if clear_marker:
            markers.pop(analysis_id, None)
        elif marker is not None and str(marker).strip():
            markers[analysis_id] = str(marker).strip()
    payload["display_color"] = colors
    payload["display_marker"] = markers
    store[ROW_STATES_KEY] = payload
    return read_row_states(store)


def clear_row_display(
    analysis_ids=(),
    *,
    state: MutableMapping[str, Any] | None = None,
) -> RowStates:
    store = _state(state)
    current = read_row_states(store)
    ids = set(_ids(analysis_ids))
    payload = _row_state_payload(current)
    if not ids:
        payload["display_color"] = {}
        payload["display_marker"] = {}
        payload["labelled"] = []
    else:
        payload["display_color"] = {key: value for key, value in current.display_color.items() if key not in ids}
        payload["display_marker"] = {key: value for key, value in current.display_marker.items() if key not in ids}
        payload["labelled"] = [value for value in current.labelled if value not in ids]
    store[ROW_STATES_KEY] = payload
    return read_row_states(store)


def clear_row_states(state: MutableMapping[str, Any] | None = None) -> None:
    _state(state).pop(ROW_STATES_KEY, None)
