from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.db import list_datasets, list_projects
from petrolab.minerals.registry import labels as mineral_labels


def render_home_page() -> None:
    """Render the PetroLab overview page."""
    st.title("ПетроЛаб")
    st.write("Единая локальная рабочая среда для минералогических и геохимических анализов.")

    datasets = list_datasets()
    projects = list_projects()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Проектов", len(projects))
    c2.metric("Наборов данных", len(datasets))
    c3.metric("Анализов", sum(int(dataset["row_count"]) for dataset in datasets))
    c4.metric("Минералов", len({dataset["mineral_key"] for dataset in datasets}))

    st.subheader("Новая графическая логика")
    st.write(
        "В «Диаграммах» теперь есть журнальные шаблоны, фильтры по колонкам, "
        "сохранённые рецепты и профили маркеров по группам."
    )

    if not datasets:
        return

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
