from __future__ import annotations

import streamlit as st

from petrolab.db import list_projects
from petrolab.search import global_search
from petrolab.ui.layout import render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import set_active_project


def render_search_page() -> None:
    render_page_header(
        "Найти в проектах",
        "Начните здесь, если знаете хотя бы фрагмент названия. Поиск находит Sample, минералы, точки, породы и изображения во всех проектах.",
        eyebrow="Поиск",
    )
    projects = list_projects()
    by_id = {int(row["id"]): row for row in projects}
    scope = st.segmented_control("Область", ["Все проекты", "Выбранные проекты"], default="Все проекты")
    selected_ids = None
    if scope == "Выбранные проекты":
        selected_ids = st.multiselect("Проекты", list(by_id), format_func=lambda value: str(by_id[int(value)]["name"]))
    query = st.text_input("Что найти", placeholder="PG-12, апатит, Kandalaksha, BSE-03…")
    if len(query.strip()) < 2:
        st.caption("Введите минимум две буквы или цифры.")
        return
    results = global_search(query, project_ids=selected_ids)
    render_section_header("Результаты", f"Найдено: {len(results)}. Поиск не изменяет данные и не объединяет проекты.")
    if not results:
        st.info("Ничего не найдено.")
        return
    for index, result in enumerate(results):
        cols = st.columns([4, 1])
        cols[0].markdown(f"**{result['title']}**  \n{result['detail']} · {result['project_name']}")
        if cols[1].button("Открыть", key=f"global_search_{index}"):
            set_active_project(int(result["project_id"]))
            if result["kind"] == "analysis":
                st.session_state["workflow_plot_analysis_ids"] = [result["analysis_id"]]
                st.session_state["workflow_plot_dataset_ids"] = [int(result["dataset_id"])]
                navigate("plots")
            else:
                dataset_id = result.get("dataset_id")
                if dataset_id is None:
                    st.warning("У этого изображения нет набора анализов; откройте его через «Шлифы».")
                    return
                st.session_state["workflow_image_dataset_id"] = int(dataset_id)
                st.session_state["workflow_image_asset_id"] = int(result["asset_id"])
                navigate("images")
            st.rerun()
