from __future__ import annotations

import streamlit as st

from petrolab.db import connect, list_accessible_datasets
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project_id

from . import statistics as _stats
from .v0160_phase_queue_hotfix import _nested_split_pairs, _repair_nested_splits


def _dataset_count_mismatches(project_id: int, dataset_ids: tuple[int, ...]) -> list[tuple[dict, int]]:
    wanted = {int(value) for value in dataset_ids}
    datasets = {
        int(item["id"]): item
        for item in list_accessible_datasets(int(project_id))
        if int(item["id"]) in wanted
    }
    if not datasets:
        return []
    marks = ",".join("?" for _ in datasets)
    with connect() as con:
        rows = con.execute(
            f"SELECT dataset_id, COUNT(*) AS n FROM analysis_rows WHERE dataset_id IN ({marks}) GROUP BY dataset_id",
            list(datasets),
        ).fetchall()
    actual = {int(row["dataset_id"]): int(row["n"]) for row in rows}
    result: list[tuple[dict, int]] = []
    for dataset_id, dataset in datasets.items():
        stored = int(dataset.get("row_count") or 0)
        real = int(actual.get(dataset_id, 0))
        if stored != real:
            result.append((dataset, real))
    return result


def _sync_row_counts(mismatches: list[tuple[dict, int]]) -> int:
    if not mismatches:
        return 0
    with connect() as con:
        con.executemany(
            "UPDATE datasets SET row_count=? WHERE id=?",
            [(int(real), int(dataset["id"])) for dataset, real in mismatches],
        )
        con.commit()
    return len(mismatches)


def _scope_with_integrity(original, *args, **kwargs):
    scope = original(*args, **kwargs)
    if scope is None or scope.project_id is None:
        return scope
    project_id = int(scope.project_id)
    mismatches = _dataset_count_mismatches(project_id, tuple(scope.dataset_ids))
    if not mismatches:
        return scope

    details = "; ".join(
        f"{str(dataset.get('name') or dataset['id'])}: указано {int(dataset.get('row_count') or 0)}, реально {real}"
        for dataset, real in mismatches[:4]
    )
    st.error(
        "Количество анализов в метаданных не совпадает с реальными строками. "
        "Статистика не должна молча считать повреждённый/недособранный фазовый набор."
    )
    st.caption(details + ("; …" if len(mismatches) > 4 else ""))

    all_datasets = list_accessible_datasets(project_id)
    nested = _nested_split_pairs(all_datasets)
    if nested:
        st.warning(
            f"Найдены повторные фазовые разбиения: {len(nested)}. "
            "Это соответствует циклу, когда уже разобранный минерал снова попадал в «Фазы и выбросы»."
        )
        confirm = st.checkbox(
            "Вернуть точки из повторных дочерних наборов в предыдущие фазовые наборы",
            key="statistics_repair_phase_tree_confirm",
        )
        if st.button(
            "Восстановить фазовые наборы",
            type="primary",
            disabled=not confirm,
            width="stretch",
            key="statistics_repair_phase_tree",
        ):
            moved, hidden = _repair_nested_splits(project_id, nested)
            st.session_state["statistics_integrity_flash"] = (
                f"Восстановлено точек: {moved}; лишних повторных наборов убрано из проекта: {hidden}."
            )
            st.rerun()
    else:
        st.warning("Повторного фазового дерева не найдено; похоже, устарел только счётчик строк.")
        if st.button("Пересчитать счётчики наборов", width="stretch", key="statistics_sync_row_counts"):
            count = _sync_row_counts(mismatches)
            st.session_state["statistics_integrity_flash"] = f"Пересчитано счётчиков: {count}."
            st.rerun()
    return scope


def render_statistics_page() -> None:
    flash = st.session_state.pop("statistics_integrity_flash", "")
    if flash:
        st.success(str(flash))
    original = _stats.render_analysis_scope
    _stats.render_analysis_scope = lambda *args, **kwargs: _scope_with_integrity(original, *args, **kwargs)
    try:
        _stats.render_statistics_page()
    finally:
        _stats.render_analysis_scope = original
