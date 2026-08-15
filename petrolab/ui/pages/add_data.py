from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.sample_registry import create_sample, find_sample_matches
from petrolab.source_registry import create_study
from petrolab.ui.layout import render_badges, render_hint, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


_SOURCE_LABELS = {"article": "Статья", "colleague": "Данные коллеги", "other": "Другое"}


def _go(route: str) -> None:
    navigate(route)
    st.rerun()


def _field_sample_form(project_id: int) -> None:
    render_section_header("Полевые образцы", "Можно завести Sample до любой аналитики")
    render_hint("Один образец — одна строка. PetroLab проверяет похожие имена и не создаёт вероятный дубль молча.")
    text = st.text_area("Названия Sample", key="add_data_field_names", placeholder="PG-01\nPG-02\nPG-03", height=130)
    c1, c2 = st.columns(2)
    lithology = c1.text_input("Полевое название", key="add_data_field_lithology", help="Необязательно; можно заполнить позже.")
    locality = c2.text_input("Местность", key="add_data_field_locality", help="Необязательно; можно заполнить позже.")
    if st.button("Проверить и добавить", type="primary", disabled=not text.strip(), key="add_data_field_save", width="stretch"):
        names = list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))
        created = 0
        conflicts: list[tuple[str, str, str]] = []
        for name in names:
            matches = find_sample_matches(int(project_id), name)
            if matches:
                conflicts.append((name, matches[0].canonical_name, matches[0].match_kind))
                continue
            create_sample(int(project_id), name, field_lithology=lithology, locality=locality)
            created += 1
        if created:
            st.success(f"Добавлено Sample: {created}.")
        if conflicts:
            st.warning("Похожие названия не добавлены автоматически. Проверьте их в «Вся база → Порядок в базе».")
            st.dataframe(pd.DataFrame(conflicts, columns=["Введено", "Похоже на", "Почему"]), width="stretch", hide_index=True)
        if created and not conflicts:
            st.session_state["add_data_mode"] = ""
            render_badges([("Sample готовы", "success")])


def _external_source_form(project_id: int) -> None:
    render_section_header("Статья / коллега", "Шаг 1 из 2: происхождение, затем файл")
    source_type = st.segmented_control(
        "Источник", list(_SOURCE_LABELS), format_func=lambda value: _SOURCE_LABELS[value],
        default="article", key="add_data_external_type",
    ) or "article"
    title = st.text_input("Название работы / набора", key="add_data_external_title", help="Можно оставить пустым и дополнить позже.")
    c1, c2 = st.columns(2)
    doi = c1.text_input("DOI", key="add_data_external_doi", help="Необязательно.")
    citation = c2.text_input("Короткая ссылка", key="add_data_external_citation", placeholder="Reguir et al., 2009", help="Необязательно.")
    colleague = ""
    if source_type == "colleague":
        colleague = st.text_input("От кого получены данные", key="add_data_external_colleague")
    with st.expander("Библиография", expanded=False):
        authors = st.text_input("Авторы", key="add_data_external_authors")
        year = st.text_input("Год", key="add_data_external_year")
        journal = st.text_input("Журнал / организация", key="add_data_external_journal")
        notes = st.text_area("Заметка", key="add_data_external_notes")
    if st.button("Сохранить источник и перейти к файлу", type="primary", key="add_data_external_save", width="stretch"):
        study_id = create_study(
            int(project_id), source_type=source_type, title=title, doi=doi, citation=citation,
            authors=authors, year=year, journal=journal, colleague=colleague, notes=notes,
        )
        st.session_state["pending_study_id"] = int(study_id)
        st.session_state["add_data_mode"] = "external_import"
        _go("sources")


def render_add_data_page() -> None:
    project = active_project()
    render_page_header(
        "Добавить данные",
        "Единый вход для собственных измерений, опубликованных данных и полевых Sample.",
        eyebrow="Данные",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        if st.button("Проекты", type="primary", key="add_data_projects"):
            _go("projects")
        return

    render_hint("Исходные обозначения и файлы сохраняются. PetroLab спрашивает только то, что нельзя вывести безопасно; любой сценарий можно продолжить позже.")
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.markdown("### Мои анализы")
            st.caption("EPMA · EDS · LA-ICP-MS · XRF · ICP-MS")
            if st.button("Загрузить файл", type="primary", key="add_data_own", width="stretch"):
                st.session_state["add_data_mode"] = "own"
                _go("quick_import")
    with c2:
        with st.container(border=True):
            st.markdown("### Статья / коллега")
            st.caption("Источник → файл")
            if st.button("Добавить внешний источник", key="add_data_external", width="stretch"):
                st.session_state["add_data_mode"] = "external"
                st.rerun()
    with c3:
        with st.container(border=True):
            st.markdown("### Полевые Sample")
            st.caption("Sample до аналитики")
            if st.button("Добавить Sample", key="add_data_field", width="stretch"):
                st.session_state["add_data_mode"] = "field"
                st.rerun()

    mode = str(st.session_state.get("add_data_mode") or "")
    if mode == "field":
        st.divider()
        _field_sample_form(int(project["id"]))
    elif mode == "external":
        st.divider()
        _external_source_form(int(project["id"]))

    st.divider()
    render_section_header("Продолжить")
    c4, c5 = st.columns(2)
    if c4.button("Рабочий процесс", width="stretch"):
        _go("workflow")
    if c5.button("Требует внимания", width="stretch"):
        _go("attention")
