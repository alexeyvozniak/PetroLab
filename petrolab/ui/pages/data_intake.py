from __future__ import annotations

import streamlit as st

from petrolab.db import list_datasets
from petrolab.source_registry import (
    create_study,
    database_health,
    link_dataset_to_study,
    list_semantic_mappings,
    list_studies,
    upsert_semantic_mapping,
)
from petrolab.ui.layout import render_badges, render_hint, render_page_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


_SOURCE_LABELS = {
    "article": "Статья",
    "colleague": "Данные коллеги",
    "other": "Другое",
}


def _go(route: str) -> None:
    navigate(route)
    st.rerun()


def _render_entry_cards() -> None:
    st.subheader("Что вы хотите добавить?")
    c1, c2, c3 = st.columns(3)
    with c1:
        with st.container(border=True):
            st.markdown("### Мои анализы")
            st.caption("Зонд, EDS, LA-ICP-MS, XRF и другие новые измерения.")
            if st.button("Открыть импорт", type="primary", key="intake_own", width="stretch"):
                _go("sources")
    with c2:
        with st.container(border=True):
            st.markdown("### Статья / коллега")
            st.caption("Сначала сохраните происхождение данных. Сам файл можно импортировать сразу после этого.")
            st.session_state.setdefault("intake_external_open", False)
            if st.button("Добавить чужие данные", key="intake_external", width="stretch"):
                st.session_state["intake_external_open"] = True
                st.rerun()
    with c3:
        with st.container(border=True):
            st.markdown("### Образцы и точки")
            st.caption("Шлифы, зёрна, точки, кратеры и навески — с отдельными значениями каждого метода.")
            if st.button("Открыть реестр", key="intake_measurements", width="stretch"):
                _go("measurements")


def _render_external_source(project_id: int) -> None:
    if not st.session_state.get("intake_external_open"):
        return
    st.divider()
    st.subheader("Данные из статьи или от коллеги")
    render_hint("Обязательных полей нет, кроме типа источника. Библиографию можно дополнить позже.")
    source_label = st.segmented_control(
        "Источник",
        options=list(_SOURCE_LABELS),
        format_func=lambda value: _SOURCE_LABELS[value],
        default="article",
        key="intake_source_type",
    ) or "article"
    title = st.text_input("Название работы / набора", key="intake_source_title")
    doi = st.text_input("DOI", key="intake_source_doi", help="Можно оставить пустым и заполнить позже.")
    citation = st.text_input("Короткая ссылка", key="intake_source_citation", placeholder="Reguir et al., 2009")
    colleague = ""
    if source_label == "colleague":
        colleague = st.text_input("От кого получены данные", key="intake_colleague")
    with st.expander("Дополнительные сведения"):
        authors = st.text_input("Авторы", key="intake_authors")
        year = st.text_input("Год", key="intake_year")
        journal = st.text_input("Журнал / организация", key="intake_journal")
        notes = st.text_area("Заметка", key="intake_source_notes")
    left, right = st.columns([1, 1])
    if left.button("Сохранить источник", type="primary", key="save_external_source", width="stretch"):
        study_id = create_study(
            project_id,
            source_type=source_label,
            title=title,
            doi=doi,
            citation=citation,
            authors=authors,
            year=year,
            journal=journal,
            colleague=colleague,
            notes=notes,
        )
        st.session_state["pending_study_id"] = study_id
        st.success("Источник сохранён. Теперь импортируйте файл; привязать его можно после импорта одним выбором.")
    if right.button("Перейти к импорту", key="external_to_import", width="stretch"):
        _go("sources")


def _study_label(row: dict) -> str:
    name = str(row.get("citation") or row.get("title") or row.get("colleague") or f"Источник {row['id']}")
    kind = _SOURCE_LABELS.get(str(row.get("source_type") or "other"), "Источник")
    return f"{kind}: {name}"


def _render_linking(project_id: int) -> None:
    studies = list_studies(project_id)
    datasets = list_datasets(project_id)
    if not studies or not datasets:
        return
    st.subheader("Связать импортированный набор с источником")
    render_hint("Это не меняет анализы. Связь нужна только для provenance и дальнейшей гармонизации.")
    study_by_id = {int(row["id"]): row for row in studies}
    dataset_by_id = {int(row["id"]): row for row in datasets}
    default_study = st.session_state.get("pending_study_id")
    study_ids = list(study_by_id)
    study_index = study_ids.index(default_study) if default_study in study_ids else 0
    c1, c2 = st.columns(2)
    dataset_id = c1.selectbox(
        "Набор данных",
        list(dataset_by_id),
        format_func=lambda value: str(dataset_by_id[int(value)]["name"]),
        key="link_external_dataset",
    )
    study_id = c2.selectbox(
        "Источник",
        study_ids,
        index=study_index,
        format_func=lambda value: _study_label(study_by_id[int(value)]),
        key="link_external_study",
    )
    source_table = st.text_input("Таблица / Supplementary sheet", key="link_source_table", help="Необязательно.")
    if st.button("Связать", type="primary", key="link_dataset_study"):
        link_dataset_to_study(int(dataset_id), int(study_id), source_table=source_table)
        st.success("Набор связан с источником.")


def _render_semantic_helper(project_id: int) -> None:
    studies = list_studies(project_id)
    if not studies:
        return
    st.subheader("Авторские обозначения")
    render_hint(
        "Необязательно разбирать их сразу. Исходное обозначение сохраняется всегда; сопоставление действует только внутри выбранного источника."
    )
    by_id = {int(row["id"]): row for row in studies}
    study_id = st.selectbox(
        "Источник для словаря",
        list(by_id),
        format_func=lambda value: _study_label(by_id[int(value)]),
        key="semantic_study",
    )
    with st.expander("Добавить или изменить одно соответствие"):
        domain = st.selectbox("Тип", ["morphology", "generation", "mineral", "rock_type", "method"], key="semantic_domain")
        source_label = st.text_input("Как написано у автора", key="semantic_source_label")
        normalized = st.text_input("Нормализованное значение", key="semantic_normalized", help="Например core, rim. Можно оставить пустым.")
        author_interp = st.text_input("Интерпретация автора", key="semantic_author_interp")
        user_interp = st.text_input("Моя интерпретация", key="semantic_user_interp")
        unresolved = st.checkbox("Оставить нерешённым", key="semantic_unresolved")
        if st.button("Сохранить соответствие", key="semantic_save", disabled=not source_label.strip()):
            upsert_semantic_mapping(
                int(study_id), domain=domain, source_label=source_label,
                normalized_value=normalized, author_interpretation=author_interp,
                user_interpretation=user_interp,
                status="unresolved" if unresolved else "resolved",
            )
            st.success("Сохранено. Исходное обозначение не изменено.")
            st.rerun()
    mappings = list_semantic_mappings(int(study_id))
    if mappings:
        st.dataframe(
            [
                {
                    "Тип": row["domain"], "У автора": row["source_label"],
                    "Нормализовано": row["normalized_value"],
                    "Автор": row["author_interpretation"], "Моя интерпретация": row["user_interpretation"],
                    "Статус": row["status"],
                }
                for row in mappings
            ],
            width="stretch", hide_index=True,
        )


def _render_health(project_id: int) -> None:
    st.subheader("Порядок в базе")
    health = database_health(project_id)
    score = int(health["score"])
    render_badges([
        (f"Состояние базы · {score}%", "success" if score >= 90 else "warning"),
        (f"Требуют внимания · {health['issue_count']}", "neutral"),
    ])
    if not health["issues"]:
        st.success("Сейчас нет известных проблем, требующих ручного разбора.")
        return
    for index, issue in enumerate(health["issues"]):
        with st.container(border=True):
            st.markdown(f"**{issue.title}** · {issue.count}")
            st.caption(issue.detail)


def render_data_intake_page() -> None:
    project = active_project()
    context = str(project["name"]) if project else "Проект не выбран"
    render_page_header(
        "Добавить данные",
        "Один простой вход для своих анализов, чужих таблиц и полевых образцов.",
        eyebrow="Данные",
        context=context,
    )
    if project is None:
        st.info("Сначала создайте проект.")
        return
    project_id = int(project["id"])
    _render_entry_cards()
    _render_external_source(project_id)
    st.divider()
    tab_sources, tab_semantics, tab_health = st.tabs(["Источники", "Авторские обозначения", "Порядок в базе"])
    with tab_sources:
        studies = list_studies(project_id)
        if studies:
            st.dataframe(
                [
                    {
                        "Тип": _SOURCE_LABELS.get(str(row["source_type"]), "Другое"),
                        "Источник": row["citation"] or row["title"] or row["colleague"] or f"Источник {row['id']}",
                        "DOI": row["doi"], "Наборов": row["dataset_count"],
                    }
                    for row in studies
                ],
                width="stretch", hide_index=True,
            )
        else:
            st.caption("Источников пока нет.")
        _render_linking(project_id)
    with tab_semantics:
        _render_semantic_helper(project_id)
    with tab_health:
        _render_health(project_id)
