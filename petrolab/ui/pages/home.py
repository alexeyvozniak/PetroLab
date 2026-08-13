from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.db import list_datasets, list_projects
from petrolab.minerals.registry import labels as mineral_labels
from petrolab.release_notes import RELEASE_NOTES
from petrolab.services.rock_service import rock_summary
from petrolab.settings_service import load_settings


def render_home_page() -> None:
    """Render a compact task-oriented PetroLab overview."""
    st.title("ПетроЛаб")
    st.write("Локальное рабочее место для минералогии, валовой геохимии, изображений, статистики и публикационных рисунков.")

    datasets = list_datasets()
    projects = list_projects()
    rocks = rock_summary()

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Проектов", len(projects))
    c2.metric("Наборов", len(datasets))
    c3.metric("Анализов", sum(int(dataset["row_count"]) for dataset in datasets))
    c4.metric("Минералов", len({dataset["mineral_key"] for dataset in datasets}))
    c5.metric("Пород", len(rocks))

    st.subheader("Основной путь")
    w1, w2, w3, w4 = st.columns(4)
    w1.markdown("**1 · Данные**\n\nExcel минералов или валовые составы пород. Проверьте единицы и семантику Fe.")
    w2.markdown("**2 · Расчёт**\n\nAPFU/end-members сохраняются отдельным derived-слоем и не подменяют исходный анализ.")
    w3.markdown("**3 · Исследование**\n\nXY, ternary, kimberlite presets, REE/spider, статистика, PCA и кластеры.")
    w4.markdown("**4 · Публикация**\n\nЖурнальные preset'ы рисунков и таблиц, интерактивный отбор и SVG/PNG/XLSX экспорт.")

    st.info(
        "Исходные анализы, расчётные параметры и локальная интерпретация разделены. "
        "Фильтры, кластеры и рабочие группы не удаляют точки из лабораторного Excel."
    )

    settings = load_settings()
    if settings.get("show_release_notes_on_home", True) and RELEASE_NOTES:
        latest = RELEASE_NOTES[0]
        with st.expander(f"Что нового · v{latest.version} · {latest.title}", expanded=False):
            for item in latest.items:
                st.markdown(f"- {item}")
            st.caption("Полная история находится в разделе «Что нового».")

    if not datasets:
        st.caption("Для минералов начните с «Источники и импорт». Для пород — с раздела «Породы».")
        return

    st.subheader("Последние наборы данных")
    view = pd.DataFrame(datasets)[
        ["project_name", "name", "mineral_key", "row_count", "source_filename", "source_sheet", "source_kind"]
    ].copy()
    view["mineral_key"] = view["mineral_key"].map(mineral_labels()).fillna(view["mineral_key"])
    view.columns = ["Проект", "Набор", "Минерал", "Строк", "Источник", "Лист", "Тип связи"]
    st.dataframe(view.tail(50), width="stretch", hide_index=True, height=360)
