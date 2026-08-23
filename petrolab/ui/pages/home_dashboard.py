from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.db import list_accessible_datasets
from petrolab.derived import formula_status
from petrolab.minerals.registry import labels as mineral_labels
from petrolab.project_checklist import (
    create_project_checklist_item,
    list_project_checklist_items,
    set_project_checklist_item_completed,
)
from petrolab.project_health import project_health
from petrolab.repositories.image_repository import list_image_records
from petrolab.services.rock_service import rock_summary
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


def _go(route: str) -> None:
    navigate(route)
    st.rerun()


TASK_DESTINATIONS = {
    "Открыть вручную позже": "",
    "Добавить данные": "add_data",
    "Анализы": "analyses",
    "Шлифы": "slides",
    "Графики": "plots",
    "Требует внимания": "attention",
}


def _dataset_label(dataset: dict) -> str:
    source = str(dataset.get("source_sheet") or "").strip()
    return f"{dataset['name']} · {source}" if source else str(dataset["name"])


def _render_project_checklist(project_id: int, datasets: list[dict]) -> None:
    """Render the personal, reversible next-actions list on the first screen."""
    render_section_header(
        "Следующие действия",
        "Личный список по активному проекту. Выполненные пункты скрываются, но остаются в журнале.",
    )
    by_dataset_id = {int(dataset["id"]): dataset for dataset in datasets}
    dataset_choices = [None, *by_dataset_id]
    with st.form("home_project_checklist_form", clear_on_submit=True):
        title = st.text_input(
            "Что нужно сделать?",
            placeholder="Например: разобрать LA-ICP-MS для 19 ТР-1",
        )
        left, right = st.columns(2)
        dataset_id = left.selectbox(
            "Связать с набором (необязательно)",
            dataset_choices,
            format_func=lambda value: "Без привязки" if value is None else _dataset_label(by_dataset_id[int(value)]),
        )
        destination = right.selectbox("Где выполнить", list(TASK_DESTINATIONS))
        note = st.text_input("Пояснение (необязательно)", placeholder="Что именно проверить или подготовить")
        submitted = st.form_submit_button("Добавить в список", type="primary")
    if submitted:
        try:
            create_project_checklist_item(
                project_id,
                title=title,
                note=note,
                dataset_id=None if dataset_id is None else int(dataset_id),
                target_route=TASK_DESTINATIONS[destination],
            )
        except ValueError as exc:
            st.error(str(exc))
        else:
            st.rerun()

    active = list_project_checklist_items(project_id)
    if not active:
        st.caption("Открытых задач нет. Добавьте следующую операцию, пока она не потерялась среди файлов и измерений.")
    for item in active:
        item_id = int(item["id"])
        checkbox_key = f"home_project_task_done_{item_id}"
        tick, body, action = st.columns([0.55, 3.25, 1.1], vertical_alignment="center")
        with tick:
            done = st.checkbox("Готово", key=checkbox_key)
        with body:
            st.markdown(f"**{item['title']}**")
            details: list[str] = []
            if item.get("dataset_name"):
                details.append(f"Набор: {item['dataset_name']}")
            if item.get("note"):
                details.append(str(item["note"]))
            if details:
                st.caption(" · ".join(details))
        with action:
            route = str(item.get("target_route") or "")
            if route and st.button("Открыть", key=f"home_project_task_open_{item_id}", width="stretch"):
                _go(route)
        if done:
            set_project_checklist_item_completed(project_id, item_id, completed=True)
            st.session_state.pop(checkbox_key, None)
            st.rerun()

    completed = list_project_checklist_items(project_id, completed=True, limit=12)
    if completed:
        with st.expander(f"Выполнено · {len(completed)}", expanded=False):
            for item in completed:
                item_id = int(item["id"])
                left, right = st.columns([4, 1], vertical_alignment="center")
                with left:
                    st.markdown(f"~~{item['title']}~~")
                with right:
                    if st.button("Вернуть", key=f"home_project_task_restore_{item_id}", width="stretch"):
                        set_project_checklist_item_completed(project_id, item_id, completed=False)
                        st.session_state.pop(f"home_project_task_done_{item_id}", None)
                        st.rerun()


def render_home_dashboard_page() -> None:
    project = active_project()
    if project is None:
        render_page_header("ПетроЛаб", "Локальное научное рабочее пространство.", eyebrow="Научный дашборд")
        st.info("Создайте первый проект. После этого PetroLab сам предложит следующий разумный шаг.")
        if st.button("Создать проект", type="primary"):
            _go("projects")
        return

    project_id = int(project["id"])
    datasets = list_accessible_datasets(project_id)
    analyses = sum(int(item.get("row_count") or 0) for item in datasets)
    images = list_image_records(project_id=project_id)
    stale = sum(int(formula_status(int(item["id"])).stale_rows) for item in datasets)
    health = project_health(project_id)
    context = f"{project['name']} · {len(datasets)} наборов · {analyses:,} анализов".replace(",", " ")
    render_page_header(
        "ПетроЛаб",
        "Минералогия, геохимия, изображения, расчёты и публикационные данные в одном рабочем пространстве.",
        eyebrow="Научный дашборд",
        context=context,
    )

    render_section_header("Что делать сейчас", "PetroLab предлагает путь, но любой модуль можно открыть напрямую")
    actions = [
        ("01 · Рабочий процесс", "Продолжить выбранный набор от контекста до первых графиков", "workflow"),
        ("02 · Добавить данные", "Свои анализы, статья/коллега или полевые Sample", "add_data"),
        ("03 · Требует внимания", f"Важных хвостов: {health['required_count']}", "attention"),
        ("04 · Массовые действия", "Исправить фазу, Generation или морфологию у группы точек", "batch_edit"),
    ]
    cols = st.columns(4)
    for index, (col, (title, note, route)) in enumerate(zip(cols, actions)):
        with col:
            st.markdown(f"**{title}**")
            st.caption(note)
            if st.button(
                "Открыть", key=f"home_{route}",
                type="primary" if index == 0 else "secondary", width="stretch",
            ):
                _go(route)

    _render_project_checklist(project_id, datasets)

    render_section_header("Состояние проекта")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Анализов", f"{analyses:,}".replace(",", " "))
    m2.metric("Наборов", len(datasets))
    m3.metric("Изображений", len(images))
    m4.metric("Порядок", f"{health['score']}%")
    render_badges([
        (f"{len({item['mineral_key'] for item in datasets})} минералогических модулей", "accent"),
        (f"{len(rock_summary(project_id))} пород", "neutral"),
        ("Расчёты актуальны" if stale == 0 else f"Пересчитать формулы · {stale}", "success" if stale == 0 else "warning"),
        ("Нет важных хвостов" if not health["required_count"] else f"Требуют внимания · {health['required_count']}", "success" if not health["required_count"] else "warning"),
    ])
    if health["required_count"]:
        if st.button("Разобрать важные хвосты", key="home_attention_now", width="stretch"):
            _go("attention")

    render_section_header("Последние наборы", "Активный проект")
    if not datasets:
        st.info("В проекте пока нет аналитических наборов.")
        if st.button("Добавить первые данные", type="primary", key="home_first_data"):
            _go("add_data")
        return
    view = pd.DataFrame(datasets)[["name", "mineral_key", "row_count", "source_filename", "source_sheet", "source_kind"]].copy()
    view["mineral_key"] = view["mineral_key"].map(mineral_labels()).fillna(view["mineral_key"])
    view["source_kind"] = view["source_kind"].map({
        "linked": "Связанный исходный файл",
        "managed_copy": "Рабочая копия PetroLab",
        "upload": "Загруженный файл",
        "collaboration_import": "Импорт из проекта",
    }).fillna("Источник без обратной синхронизации")
    view.columns = ["Набор", "Минерал", "Строк", "Источник", "Лист", "Связь"]
    st.dataframe(view.head(12), width="stretch", hide_index=True, height=390)
