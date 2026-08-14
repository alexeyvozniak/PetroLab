from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analytical_sessions import TECHNIQUES, list_sessions
from petrolab.measurement_registry import add_observation, create_entity, list_entities, list_observations
from petrolab.sample_registry import list_samples
from petrolab.ui.layout import render_badges, render_hint, render_page_header, render_section_header
from petrolab.ui.project_context import active_project_id


ENTITY_LABELS = {
    "thin_section": "Шлиф",
    "grain": "Зерно",
    "probe_point": "Зондовая точка",
    "la_crater": "LA-кратер",
    "aliquot": "Фракция / навеска",
}
QUALIFIERS = ["", "<", "≤", ">", "≥"]


def _entity_label(row: dict) -> str:
    parent = f" ← {row['parent_name']}" if row.get("parent_name") else ""
    sample = f" · {row['sample_name']}" if row.get("sample_name") else ""
    return f"{ENTITY_LABELS.get(str(row['kind']), row['kind'])}: {row['name']}{parent}{sample}"


def _create_entity_form(project_id: int, entities: list[dict]) -> None:
    with st.expander("Добавить физическую сущность", expanded=not entities):
        render_hint("Сущности описывают физические объекты. Они не заменяют строки таблицы и позволяют хранить несколько независимых измерений одного элемента.")
        samples = list_samples(project_id)
        by_sample = {int(row["id"]): row for row in samples}
        by_entity = {int(row["id"]): row for row in entities}
        with st.form("measurement_new_entity", clear_on_submit=True):
            left, right = st.columns(2)
            kind = left.selectbox("Тип", list(ENTITY_LABELS), format_func=lambda value: ENTITY_LABELS[value])
            name = right.text_input("Название", placeholder="например, Gr-4 или P-17")
            sample_id = left.selectbox(
                "Образец", [0] + list(by_sample),
                format_func=lambda value: "Не привязывать пока" if value == 0 else str(by_sample[int(value)]["name"]),
            )
            parent_id = right.selectbox(
                "Родительская сущность", [0] + list(by_entity),
                format_func=lambda value: "Нет" if value == 0 else _entity_label(by_entity[int(value)]),
            )
            description = st.text_area("Заметка", placeholder="Зона, текстурная позиция, координаты…", height=70)
            submitted = st.form_submit_button("Сохранить сущность", type="primary")
        if submitted:
            try:
                create_entity(
                    project_id, kind=kind, name=name,
                    sample_id=int(sample_id) or None, parent_id=int(parent_id) or None,
                    description=description,
                )
                st.success("Сущность сохранена.")
                st.rerun()
            except (ValueError, TypeError) as exc:
                st.error(str(exc))


def _add_observation_form(project_id: int, entities: list[dict]) -> None:
    with st.expander("Добавить измерение", expanded=bool(entities)):
        if not entities:
            st.info("Сначала добавьте хотя бы одну сущность: например зерно, зондовую точку или LA-кратер.")
            return
        by_entity = {int(row["id"]): row for row in entities}
        sessions = list_sessions(project_id)
        by_session = {int(row["id"]): row for row in sessions}
        with st.form("measurement_new_observation", clear_on_submit=True):
            entity_id = st.selectbox("Где измерено", list(by_entity), format_func=lambda value: _entity_label(by_entity[int(value)]))
            c1, c2, c3 = st.columns(3)
            analyte = c1.text_input("Аналит", placeholder="Ti")
            reported_form = c2.text_input("Как записан", placeholder="TiO2")
            method = c3.text_input("Метод", placeholder="EPMA-WDS, LA-ICP-MS, TIMS")
            c1, c2, c3, c4 = st.columns(4)
            value_text = c1.text_input("Значение", placeholder="1.15")
            qualifier = c2.selectbox("Знак", QUALIFIERS)
            unit = c3.text_input("Единица", placeholder="wt.% / µg/g / ppm")
            uncertainty_text = c4.text_input("± неопределённость", placeholder="необязательно")
            c1, c2 = st.columns(2)
            session_id = c1.selectbox(
                "Аналитическая сессия", [0] + list(by_session),
                format_func=lambda value: "Не указана" if value == 0 else f"{by_session[int(value)]['name']} · {TECHNIQUES.get(by_session[int(value)]['technique'], by_session[int(value)]['technique'])}",
            )
            instrument = c2.text_input("Прибор / режим", placeholder="необязательно")
            c1, c2 = st.columns(2)
            standard = c1.text_input("Стандарт", placeholder="необязательно")
            note = c2.text_input("Источник / заметка", placeholder="таблица, строка, комментарий")
            submitted = st.form_submit_button("Сохранить измерение", type="primary")
        if submitted:
            try:
                value = float(value_text.replace(",", ".")) if value_text.strip() else None
                uncertainty = float(uncertainty_text.replace(",", ".")) if uncertainty_text.strip() else None
                add_observation(
                    project_id, entity_id=int(entity_id), analyte=analyte, reported_form=reported_form,
                    value=value, qualifier=qualifier, unit=unit, uncertainty=uncertainty,
                    method=method, session_id=int(session_id) or None, instrument=instrument,
                    standard_name=standard, source_note=note,
                )
                st.success("Измерение сохранено отдельно от остальных методов.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))


def _render_registry(project_id: int, entities: list[dict]) -> None:
    observations = list_observations(project_id)
    entity_by_id = {int(row["id"]): row for row in entities}
    session_by_id = {int(row["id"]): row for row in list_sessions(project_id)}
    render_badges([
        (f"{len(entities)} физических сущностей", "accent"),
        (f"{len(observations)} измерений", "neutral"),
        ("Значения разных методов не объединяются", "success"),
    ])
    if entities:
        render_section_header("Структура образцов", "Иерархия нужна для ориентации; исходные таблицы остаются независимыми")
        st.dataframe(pd.DataFrame([{
            "Тип": ENTITY_LABELS.get(str(row["kind"]), str(row["kind"])),
            "Название": row["name"], "Родитель": row.get("parent_name") or "",
            "Образец": row.get("sample_name") or "", "Заметка": row.get("description") or "",
        } for row in entities]), width="stretch", hide_index=True)
    if observations:
        render_section_header("Реестр измерений", "Нет автоматического выбора «лучшего» Ti: EPMA, LA-ICP-MS и TIMS сохраняются как отдельные наблюдения")
        st.dataframe(pd.DataFrame([{
            "Сущность": entity_by_id.get(int(row.entity_id or 0), {}).get("name", ""),
            "Тип": ENTITY_LABELS.get(str(entity_by_id.get(int(row.entity_id or 0), {}).get("kind") or ""), ""),
            "Аналит": row.analyte, "Форма": row.reported_form,
            "Значение": row.value, "Знак": row.qualifier, "Единица": row.unit,
            "±": row.uncertainty, "Метод": row.method, "Прибор": row.instrument,
            "Сессия": session_by_id.get(int(row.session_id or 0), {}).get("name", ""),
            "Стандарт": row.standard_name, "Заметка": row.source_note,
        } for row in observations]), width="stretch", hide_index=True, height=420)


def render_measurements_page() -> None:
    render_page_header(
        "Образцы и измерения",
        "Физические объекты и метод-специфичные результаты. Один и тот же Ti можно сохранить для зонда, LA-ICP-MS и TIMS без потери provenance.",
        eyebrow="Данные",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала создайте проект.")
        return
    entities = list_entities(project_id)
    _create_entity_form(project_id, entities)
    _add_observation_form(project_id, entities)
    _render_registry(project_id, entities)
