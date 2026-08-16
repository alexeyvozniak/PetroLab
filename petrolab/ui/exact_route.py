"""Persistent exact-route scopes for rerun-driven pages.

A contextual action may open a page with an exact set of immutable analysis IDs.
Streamlit widgets rerun the whole page, so that scope must survive until the user
explicitly resets it. A deliberate new dataset-only route, however, replaces the
old exact scope instead of inheriting stale analysis IDs.
"""
from __future__ import annotations

from collections.abc import MutableMapping
from typing import Any

import streamlit as st


def _unique_strings(values) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values or [] if str(value)))


def _unique_ints(values) -> list[int]:
    result: list[int] = []
    for value in values or []:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number not in result:
            result.append(number)
    return result


def clear_exact_route(
    state: MutableMapping[str, Any],
    *,
    persistent_analysis_key: str,
    persistent_dataset_key: str,
    persistent_context_key: str | None = None,
) -> None:
    state.pop(persistent_analysis_key, None)
    state.pop(persistent_dataset_key, None)
    if persistent_context_key:
        state.pop(persistent_context_key, None)


def persist_exact_route(
    state: MutableMapping[str, Any],
    *,
    incoming_analysis_key: str,
    incoming_dataset_key: str,
    incoming_context_key: str | None,
    persistent_analysis_key: str,
    persistent_dataset_key: str,
    persistent_context_key: str | None,
) -> tuple[list[str], list[int], dict[str, Any]]:
    """Persist one exact routed scope and rehydrate its incoming keys on rerun."""
    has_analysis = incoming_analysis_key in state
    has_datasets = incoming_dataset_key in state

    if has_datasets and not has_analysis:
        clear_exact_route(
            state,
            persistent_analysis_key=persistent_analysis_key,
            persistent_dataset_key=persistent_dataset_key,
            persistent_context_key=persistent_context_key,
        )

    if has_analysis:
        analysis_ids = _unique_strings(state.get(incoming_analysis_key, []))
        dataset_ids = _unique_ints(state.get(incoming_dataset_key, []))
        if analysis_ids:
            state[persistent_analysis_key] = analysis_ids
            state[persistent_dataset_key] = dataset_ids
            if persistent_context_key and incoming_context_key:
                context = state.get(incoming_context_key, {})
                state[persistent_context_key] = dict(context) if isinstance(context, dict) else {}
        else:
            clear_exact_route(
                state,
                persistent_analysis_key=persistent_analysis_key,
                persistent_dataset_key=persistent_dataset_key,
                persistent_context_key=persistent_context_key,
            )

    analysis_ids = _unique_strings(state.get(persistent_analysis_key, []))
    dataset_ids = _unique_ints(state.get(persistent_dataset_key, []))
    context: dict[str, Any] = {}
    if persistent_context_key:
        raw = state.get(persistent_context_key, {})
        context = dict(raw) if isinstance(raw, dict) else {}

    if analysis_ids:
        state[incoming_analysis_key] = analysis_ids
        state[incoming_dataset_key] = dataset_ids
        if incoming_context_key:
            state[incoming_context_key] = context
    return analysis_ids, dataset_ids, context


def render_exact_route_banner(
    *,
    count: int,
    label: str,
    reset_key: str,
    persistent_keys: tuple[str, ...],
    incoming_keys: tuple[str, ...],
    extra_clear: tuple[str, ...] = (),
) -> None:
    """Explain and explicitly reset an exact routed scope."""
    if count <= 0:
        return
    st.info(
        f"Точный отбор активен: {count} анализов. "
        "Фильтры и rerun не расширяют его до всего набора."
    )
    if st.button(label, key=reset_key, width="stretch"):
        for key in (*persistent_keys, *incoming_keys, *extra_clear):
            st.session_state.pop(key, None)
        st.rerun()
