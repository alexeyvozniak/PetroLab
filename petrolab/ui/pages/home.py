from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.db import list_datasets, list_projects
from petrolab.minerals.registry import labels as mineral_labels


def render_home_page() -> None:
    """Render a task-oriented PetroLab overview."""
    st.title("ПетроЛаб")
    st.write("Единая локальная рабочая среда для минералогических и геохимических анализов.")

    datasets = list_datasets()
    projects = list_projects()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Проектов", len(projects))
    c2.metric("Наборов данных", len(datasets))
    c3.metric("Анализов", sum(int(dataset["row_count"]) for dataset in datasets))
    c4.metric("Минералов", len({dataset["mineral_key"] for dataset in datasets}))

    st.subheader("Как работать")
    w1, w2, w3, w4 = st.columns(4)
    w1.markdown("**1. Импорт**\n\nПодключите Excel и подтвердите названия служебных полей и неоднозначный Fe₂O₃.")
    w2.markdown("**2. Расчёт**\n\nВыберите минерал и метод. Сохраните apfu и другие производные поля в рабочую базу.")
    w3.markdown("**3. Диаграмма**\n\nВыберите любые исходные или расчётные величины как X/Y, группы и фильтры.")
    w4.markdown("**4. Изображения**\n\nЗагрузите пачку BSE/EDS/фото и привяжите каждый снимок к нужным точкам или зерну.")

    st.info(
        "Исходный анализ и результат пересчёта — разные слои. Поэтому Rb [µg/g] может быть "
        "построен против apfu_AlIV напрямую, но расчётный AlIV никогда не записывается как будто "
        "это исходная колонка лабораторного Excel."
    )

    if not datasets:
        st.caption("Начните с раздела «Источники и импорт».")
        return

    st.subheader("Наборы данных")
    view = pd.DataFrame(datasets)[
        [
            "project_name",
            "name",
            "mineral_key",
            "row_count",
            "source_filename",
            "source_sheet",
            "source_kind",
        ]
    ].copy()
    view["mineral_key"] = view["mineral_key"].map(mineral_labels()).fillna(view["mineral_key"])
    view.columns = ["Проект", "Набор", "Минерал", "Строк", "Источник", "Лист", "Тип связи"]
    st.dataframe(view, width="stretch", hide_index=True)
