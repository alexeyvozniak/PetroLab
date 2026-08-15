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
        "Один вход для обычного XY, нескольких синхронных графиков, совмещённых EDS/LA точек и whole-rock литературы.",
        eyebrow="Сценарий",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        return

    render_section_header("Что сравниваем", "Выберите рабочий режим, а не инструмент из длинного списка")
    cards = [
        ("Один XY", "Быстро сравнить свои и литературные минералогические анализы на одной диаграмме.", "plots"),
        ("Несколько графиков", "Одна выборка и одна легенда для 2–6 панелей; выключение статьи действует сразу везде.", "multi_panel"),
        ("EDS / EPMA + LA", "Собрать разные методы одной физической точки и сравнивать их как одну логическую строку.", "composite_points"),
        ("Породы + литература", "Whole-rock XY, REE/Spider, изотопы и проверенные tectonic presets с общими источниками.", "whole_rock_compare"),
    ]
    cols = st.columns(4)
    for index, (col, (title, note, route)) in enumerate(zip(cols, cards)):
        with col:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(note)
                if st.button(
                    "Открыть",
                    key=f"compare_mode_{route}",
                    width="stretch",
                    type="primary" if index == 1 else "secondary",
                ):
                    _go(route)

    datasets = list_accessible_datasets(int(project["id"]))
    if not datasets:
        st.info("В проекте пока нет минералогических наборов для сравнения.")
        if st.button("Добавить данные", type="primary", width="stretch"):
            _go("add_data")
        return

    render_section_header("Быстрый отбор минералогических массивов", "Можно сразу передать одинаковую выборку в один или несколько графиков")
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
    st.caption(
        "Источники, поколения и рабочие группы остаются отдельными сериями; их можно выключать или показывать как полупрозрачные точки/поля без удаления данных."
    )
    c1, c2, c3 = st.columns(3)
    disabled = len(selected) < 1
    if c1.button("Один XY", type="primary", disabled=disabled, width="stretch", key="compare_to_xy"):
        st.session_state["workflow_plot_dataset_ids"] = [int(value) for value in selected]
        st.session_state["workflow_plot_context"] = {
            "scope": "Сравнение",
            "dataset_ids": [int(value) for value in selected],
        }
        st.session_state["workflow_plot_notice"] = "В график переданы выбранные массивы для сравнения."
        _go("plots")
    if c2.button("Несколько графиков", disabled=disabled, width="stretch", key="compare_to_multi"):
        st.session_state["workflow_plot_dataset_ids"] = [int(value) for value in selected]
        st.session_state["multi_panel_data_mode"] = "Обычные анализы"
        _go("multi_panel")
    if c3.button("Сначала найти точную группу", width="stretch", key="compare_to_search"):
        _go("search")

    st.caption(
        "Например: K-HF против N-HF, апатиты из двух статей или несколько Sample. Для точечного отбора найдите группу лупой, затем передайте найденное в график."
    )


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
        "Один вход для публикационной работы: одиночный или multi-panel график, треугольная диаграмма, таблица или финальный экспорт.",
        eyebrow="Сценарий",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        return

    cards = [
        ("XY-рисунок", "Собрать выборку, настроить серии и экспортировать рисунок.", "plots"),
        ("Multi-panel", "Собрать несколько диаграмм с общей выборкой, легендой и стилями.", "multi_panel"),
        ("Треугольная диаграмма", "Построить и сохранить треугольную классификационную диаграмму.", "ternary"),
        ("Таблица для статьи", "Собрать точный отбор анализов в публикационную таблицу.", "article_tables"),
        ("Экспорт", "Скачать подготовленные результаты и файлы.", "export"),
    ]
    cols = st.columns(5)
    for index, (col, (title, note, route)) in enumerate(zip(cols, cards)):
        with col:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(note)
                if st.button("Открыть", key=f"publish_{route}", width="stretch", type="primary" if index == 0 else "secondary"):
                    _go(route)
