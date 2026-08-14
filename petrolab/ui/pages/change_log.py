from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import apply_quick_filter
from petrolab.db import list_change_log
from petrolab.edit_undo import undo_change_log_entry
from petrolab.operation_journal import list_operations, undo_operation
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project_id


def _interpretation_history(project_id: int) -> None:
    rows = list_operations(int(project_id), limit=1000)
    if not rows:
        st.caption("Массовых интерпретационных операций пока нет.")
        return
    table = pd.DataFrame([
        {
            "id": row["id"],
            "Когда": row["created_at"],
            "Действие": row["label"],
            "Точек": row["affected_count"],
            "Можно отменить": bool(row["can_undo"]) and not bool(str(row["undone_at"])),
            "Отменено": row["undone_at"],
        }
        for row in rows
    ])
    st.dataframe(table, width="stretch", hide_index=True, height=430)
    undoable = [row for row in rows if int(row["can_undo"]) and not str(row["undone_at"])]
    if not undoable:
        return
    by_id = {int(row["id"]): row for row in undoable}
    operation_id = st.selectbox(
        "Операция для отмены",
        list(by_id),
        format_func=lambda value: f"#{value} · {by_id[int(value)]['label']} · {by_id[int(value)]['affected_count']} точек",
        key="history_interpretation_undo",
    )
    confirm = st.checkbox("Я понимаю, что будет восстановлено предыдущее интерпретационное состояние", key="history_interpretation_confirm")
    if st.button("Отменить выбранную операцию", disabled=not confirm, key="history_interpretation_apply", width="stretch"):
        try:
            label = undo_operation(int(project_id), int(operation_id))
        except Exception as exc:
            st.error(f"Отмена остановлена: {exc}")
        else:
            st.success(f"Отменено: {label}")
            st.rerun()


def _raw_history(project_id: int) -> None:
    rows = list_change_log(limit=2000)
    if not rows:
        st.caption("Правок исходных/локальных значений пока нет.")
        return
    dataframe = pd.DataFrame(rows)
    query = st.text_input("Поиск", placeholder="Набор, колонка, analysis ID, старое или новое значение", key="raw_history_search")
    shown = apply_quick_filter(dataframe, query)
    synced = int(pd.to_numeric(shown.get("synced_to_source"), errors="coerce").fillna(0).sum()) if "synced_to_source" in shown else 0
    render_badges([
        (f"{len(shown)} записей", "neutral"),
        (f"{synced} синхронизировано с источником", "success" if synced else "neutral"),
    ])
    st.dataframe(shown, width="stretch", hide_index=True, height=470)
    if shown.empty or "id" not in shown.columns:
        return
    ids = [int(value) for value in shown["id"].head(200).tolist()]
    by_id = {int(row["id"]): row for row in rows if int(row["id"]) in ids}
    change_id = st.selectbox(
        "Правка для возврата",
        ids,
        format_func=lambda value: f"#{value} · {by_id[value]['column_name']} · {by_id[value]['new_value']} → {by_id[value]['old_value']}",
        key="raw_history_undo_id",
    )
    st.caption("Undo разрешён только если это значение не менялось позже. Если правка была записана в Excel, обратная запись проходит те же fingerprint/conflict проверки и создаёт backup.")
    confirm = st.checkbox("Вернуть предыдущее значение", key="raw_history_undo_confirm")
    if st.button("Отменить правку", disabled=not confirm, key="raw_history_undo_apply", width="stretch"):
        try:
            result = undo_change_log_entry(int(change_id))
        except Exception as exc:
            st.error(f"Отмена остановлена: {exc}")
        else:
            if result.ok:
                st.success("Предыдущее значение восстановлено безопасным путём.")
                for warning in result.warnings:
                    st.warning(str(warning))
                st.rerun()
            for error in result.errors:
                st.error(str(error))


def render_change_log_page() -> None:
    project_id = active_project_id()
    render_page_header(
        "История действий",
        "Интерпретации и ручные правки данных. Поддерживаемые операции можно безопасно вернуть назад.",
        eyebrow="Система",
    )
    if project_id is None:
        st.info("Сначала выберите проект.")
        return
    interpretation, raw = st.tabs(["Интерпретации", "Значения и Excel"])
    with interpretation:
        _interpretation_history(int(project_id))
    with raw:
        _raw_history(int(project_id))
