from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.derived import load_unified_with_derived
from petrolab.selections import delete_selection, list_selections, save_selection, selection_analysis_ids
from petrolab.ui.data_scope import render_analysis_scope
from petrolab.ui.layout import render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


def _open_selection(selection: dict) -> None:
    ids = selection_analysis_ids(int(selection["id"]))
    st.session_state["selection_analysis_ids"] = ids
    st.session_state["active_selection_analysis_ids"] = ids
    st.session_state["selection_name"] = str(selection["name"])
    st.session_state["workflow_table_analysis_ids"] = ids
    st.session_state["workflow_table_dataset_ids"] = []
    st.session_state["workflow_plot_analysis_ids"] = ids


def render_selections_page() -> None:
    project = active_project()
    render_page_header("Рабочие выборки", "Сохранённые отборы для графиков, шлифов, таблиц и проверки интерпретаций.", eyebrow="Selection")
    if project is None:
        st.info("Сначала выберите проект.")
        return
    project_id = int(project["id"])
    render_section_header("Сохранить текущий отбор", "Точки остаются исходными измерениями; сохраняется только ваш исследовательский вопрос")
    scope = render_analysis_scope("selection_create", allow_all_projects=False)
    if scope is not None and not scope.dataframe.empty:
        frame = scope.dataframe
        st.caption(f"Текущий отбор: {len(frame)} точек.")
        left, right = st.columns([1, 1])
        name = left.text_input("Название выборки", placeholder="Апатиты из статьи X")
        note = right.text_input("Заметка", placeholder="Для сравнения и Figure 3")
        if st.button("Сохранить выборку", type="primary", disabled=not name, key="save_working_selection"):
            save_selection(project_id, name=name, analysis_ids=frame["_analysis_id"].astype(str).tolist(), note=note, context={"dataset_ids": scope.dataset_ids})
            st.success("Выборка сохранена. Её можно открыть в графиках, шлифах или таблицах.")
            st.rerun()
    render_section_header("Мои выборки", "Открыть, передать в публикационные таблицы или удалить без влияния на химические данные")
    records = list_selections(project_id)
    if not records:
        st.caption("Сохранённых выборок пока нет.")
        return
    for record in records:
        cols = st.columns([3, 1, 1, 1])
        cols[0].markdown(f"**{record['name']}**  \n{record['member_count']} точек · {record['note'] or 'без заметки'}")
        if cols[1].button("В графики", key=f"selection_plot_{record['id']}"):
            _open_selection(record)
            navigate("plots")
            st.rerun()
        if cols[2].button("В таблицу", key=f"selection_table_{record['id']}"):
            ids = selection_analysis_ids(int(record["id"]))
            full = load_unified_with_derived(None)
            selected = full[full["_analysis_id"].astype(str).isin(ids)] if not full.empty else pd.DataFrame()
            st.session_state["workflow_table_analysis_ids"] = ids
            st.session_state["workflow_table_dataset_ids"] = [int(value) for value in selected.get("_dataset_id", pd.Series(dtype=int)).dropna().unique()]
            navigate("article_tables")
            st.rerun()
        if cols[3].button("Удалить", key=f"selection_delete_{record['id']}"):
            delete_selection(int(record["id"]))
            st.rerun()
