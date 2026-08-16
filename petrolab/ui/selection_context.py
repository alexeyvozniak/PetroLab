from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, MutableMapping


SELECTION_KEY = "_petrolab_selection_context"
ROW_STATES_KEY = "_petrolab_row_states"

_SELECTION_MODES = {"replace", "add", "subtract"}
_ROW_STATE_KINDS = {"hidden", "excluded"}


@dataclass(frozen=True)
class SelectionContext:
    """Canonical transient scientific selection shared by all PetroLab views.

    Selection is intentionally distinct from filtering, hidden/excluded row states,
    Work Group and Generation.  Only immutable ``analysis_id`` values cross views.
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
    """JMP-like row states that do not change the active selection."""

    hidden: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()


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
    )


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
    payload = {
        "hidden": list(current.hidden),
        "excluded": list(current.excluded),
    }
    payload[kind] = list(updated)
    store[ROW_STATES_KEY] = payload
    return read_row_states(store)


def clear_row_states(state: MutableMapping[str, Any] | None = None) -> None:
    _state(state).pop(ROW_STATES_KEY, None)
