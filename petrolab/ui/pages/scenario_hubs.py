from __future__ import annotations

import streamlit as st

from petrolab.db import list_accessible_datasets
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


def _go(route: str) -> None:
    navigate(route)
    st.rerun()


def _dataset_label(dataset: dict) -> str:
    name = str(dataset.get("name") or f"Набор {dataset['id']}")
    mineral = str(dataset.get("mineral_key") or "generic")
    rows = int(dataset.get("row_count") or 0)
    return f"{name} · {mineral} · {rows} строк"


def render_compare_page() -> None:
    project = active_project()
    render_page_header(
        "Сравнить данные",
        "Выберите массивы, которые хотите видеть вместе. Дальше PetroLab передаст их в один график как отдельные группы, которые можно включать и выключать.",
        eyebrow="Сценарий",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        return
    datasets = list_accessible_datasets(int(project["id"]))
    if not datasets:
        st.info("В проекте пока нет данных для сравнения.")
        if st.button("Добавить данные", type="primary", width="stretch"):
            _go("add_data")
        return

    by_id = {int(item["id"]): item for item in datasets}
    selected = st.multiselect(
        "Что сравниваем",
        list(by_id),
        format_func=lambda value: _dataset_label(by_id[int(value)]),
        key="compare_dataset_ids",
        placeholder="Выберите два или больше массивов",
    )
    if selected:
        render_badges([(f"выбрано массивов · {len(selected)}", "accent")])
    st.caption("На XY-диаграмме источники, поколения и другие группы остаются отдельными сериями; ненужную серию можно скрыть без удаления данных.")
    c1, c2 = st.columns(2)
    if c1.button("Сравнить на XY", type="primary", disabled=len(selected) < 2, width="stretch"):
        st.session_state["workflow_plot_dataset_ids"] = [int(value) for value in selected]
        st.session_state["workflow_plot_context"] = {
            "scope": "Сравнение",
            "dataset_ids": [int(value) for value in selected],
        }
        st.session_state["workflow_plot_notice"] = "В график переданы выбранные массивы для сравнения."
        _go("plots")
    if c2.button("Сначала найти конкретные группы", width="stretch"):
        _go("search")

    render_section_header("Если вы уже знаете, что сравнивать")
    st.caption("Например: апатиты из двух статей, K-HF против N-HF, отдельные Sample или поколения. Для такого отбора удобнее сначала воспользоваться поиском, а затем передать найденное в график.")


def render_calculate_page() -> None:
    project = active_project()
    render_page_header(
        "Посчитать",
        "Выберите не метод из длинного списка, а тип задачи. PetroLab покажет подходящие расчёты дальше.",
        eyebrow="Сценарий",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        return

    cards = [
        ("Формулы и APFU", "Структурные формулы и пересчёты для минералогических модулей.", "formulae"),
        ("Температура · давление · fO₂", "Мономинеральные и минерал–расплав методы; без биминеральных методов.", "thermobarometry"),
        ("Минералогические расчёты", "Классификации и специализированные модули минералов.", "minerals"),
    ]
    cols = st.columns(3)
    for col, (title, note, route) in zip(cols, cards):
        with col:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(note)
                if st.button("Открыть", key=f"calculate_{route}", width="stretch", type="primary" if route == "thermobarometry" else "secondary"):
                    _go(route)


def render_publish_page() -> None:
    project = active_project()
    render_page_header(
        "Подготовить рисунок или таблицу",
        "Один вход для публикационной работы: график, треугольная диаграмма, таблица или финальный экспорт.",
        eyebrow="Сценарий",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        return

    cards = [
        ("XY-рисунок", "Собрать выборку, настроить серии и экспортировать рисунок.", "plots"),
        ("Треугольная диаграмма", "Построить и сохранить треугольную классификационную диаграмму.", "ternary"),
        ("Таблица для статьи", "Собрать точный отбор анализов в публикационную таблицу.", "article_tables"),
        ("Экспорт", "Скачать подготовленные результаты и файлы.", "export"),
    ]
    cols = st.columns(4)
    for index, (col, (title, note, route)) in enumerate(zip(cols, cards)):
        with col:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(note)
                if st.button("Открыть", key=f"publish_{route}", width="stretch", type="primary" if index == 0 else "secondary"):
                    _go(route)
