from __future__ import annotations

import io
import json

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_datasets, list_plot_recipes, list_style_profiles
from petrolab.derived import formula_provenance_rows, load_unified_with_derived
from petrolab.figure_recipes import list_figure_recipes
from petrolab.services.image_service import image_export_records
from petrolab.ui.layout import render_badges, render_page_header, render_work_context
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project

from . import export as _legacy
from . import figure_recipes as _figure_ui


def _render_figure_export() -> None:
    project = active_project()
    if project is None:
        st.info("Сначала выберите проект.")
        return
    project_id = int(project["id"])
    recipes = list_figure_recipes(project_id)
    plots = list_plot_recipes(project_id)
    render_badges([
        (f"{len(recipes)} figure recipes", "accent"),
        (f"{len(plots)} сохранённых панелей", "neutral"),
    ])
    render_work_context(
        area=f"публикация · {project['name']}",
        note="Панели остаются воспроизводимыми; PNG/PDF собирается только на финальном шаге",
    )

    if not recipes:
        st.markdown("#### Сначала соберите Figure Recipe")
        st.caption("Выберите сохранённые XY, ternary и REE/spider панели, задайте порядок A–F и подписи. После этого здесь появится финальный preview и экспорт.")
        if st.button("Создать Figure Recipe", type="primary", key="export_reference_new_figure"):
            navigate("figure_recipes")
            st.rerun()
        return

    labels = {
        f"{record['name']} · {record['layout_name']} · {record.get('updated_at', '')}": record
        for record in recipes
    }
    selected_label = st.selectbox("Figure Recipe", list(labels), key="export_reference_recipe")
    record = labels[selected_label]

    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        st.markdown("#### Компоновка")
        cells = pd.DataFrame(record["cells"])
        st.dataframe(cells, width="stretch", hide_index=True, height=min(360, 48 + 36 * len(cells)))
        if st.button("Изменить панели и подписи", key="export_reference_edit_figure", width="stretch"):
            navigate("figure_recipes")
            st.rerun()
    with right:
        st.markdown("#### Перед экспортом")
        st.checkbox("Проверены подписи A–F", key="export_reference_check_labels")
        st.checkbox("Проверены единицы и оси", key="export_reference_check_axes")
        st.checkbox("Проверены источники и выборка", key="export_reference_check_sources")
        st.caption("Исходные SVG остаются отдельными векторными файлами; composite предназначен для финальной сборки и рецензирования.")

    _figure_ui._render_composer(record)


def _render_article_tables() -> None:
    st.markdown("#### Таблицы и Supplementary")
    st.caption("Используйте ту же рабочую Selection, что и на графиках. Таблица не меняет исходный Excel и сохраняет provenance набора.")
    c1, c2 = st.columns([1, 1])
    if c1.button("Открыть таблицы для статьи", type="primary", key="export_reference_article_tables", width="stretch"):
        navigate("article_tables")
        st.rerun()
    if c2.button("Открыть Figure Recipe", key="export_reference_figure_recipe", width="stretch"):
        navigate("figure_recipes")
        st.rerun()
    st.markdown(
        '<div class="pd-note-card">Для статьи лучше сохранять не один «финальный файл», а воспроизводимый набор: '
        'Selection + recipe графика + таблица + figure manifest.</div>',
        unsafe_allow_html=True,
    )


def _render_database_export() -> None:
    datasets = list_datasets()
    if not datasets:
        st.info("Пока нечего экспортировать.")
        return

    labels = {dataset_label(dataset): int(dataset["id"]) for dataset in datasets}
    selected = st.multiselect("Наборы данных", list(labels), default=list(labels), key="export_reference_datasets")
    dataset_ids = [labels[label] for label in selected]
    if not dataset_ids:
        st.info("Выберите хотя бы один набор.")
        return

    project_ids = _legacy._selected_project_ids(dataset_ids)
    dataframe = load_unified_with_derived(dataset_ids=dataset_ids)
    render_badges([
        (f"{len(dataframe):,} строк".replace(",", " "), "accent"),
        (f"{len(dataset_ids)} наборов", "neutral"),
        (f"{len(project_ids)} проектов", "neutral"),
    ])
    preview_columns = [column for column in dataframe.columns if not str(column).startswith("_")]
    st.dataframe(dataframe[preview_columns].head(100), width="stretch", hide_index=True, height=360)
    st.caption(f"Показаны первые {min(100, len(dataframe))} строк. В Excel попадут все выбранные строки и связанный provenance.")

    export_dataframe = dataframe[preview_columns].copy()
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export_dataframe.to_excel(writer, index=False, sheet_name="Все анализы")

        memberships = _legacy._selected_membership_rows(dataset_ids)
        if memberships:
            pd.DataFrame(memberships).to_excel(writer, index=False, sheet_name="Проекты datasets")

        images = _legacy._dataset_scoped_records(image_export_records(), dataset_ids)
        if images:
            pd.DataFrame(images).to_excel(writer, index=False, sheet_name="Изображения")

        provenance = formula_provenance_rows(dataset_ids)
        if provenance:
            pd.DataFrame(provenance).to_excel(writer, index=False, sheet_name="Методы пересчёта")

        recipes = _legacy._project_scoped_records(list_plot_recipes(), project_ids)
        if recipes:
            pd.DataFrame([
                {
                    "id": record["id"],
                    "project_id": record["project_id"],
                    "name": record["name"],
                    "created_at": record["created_at"],
                    "updated_at": record["updated_at"],
                    "config": json.dumps(record["config"], ensure_ascii=False),
                }
                for record in recipes
            ]).to_excel(writer, index=False, sheet_name="Рецепты графиков")

        profiles = _legacy._project_scoped_records(list_style_profiles(), project_ids)
        if profiles:
            pd.DataFrame([
                {
                    "id": record["id"],
                    "project_id": record["project_id"],
                    "name": record["name"],
                    "grouping_column": record["grouping_column"],
                    "created_at": record["created_at"],
                    "updated_at": record["updated_at"],
                    "styles": json.dumps(record["styles"], ensure_ascii=False),
                }
                for record in profiles
            ]).to_excel(writer, index=False, sheet_name="Профили стилей")

    st.download_button(
        "Скачать единый Excel",
        buffer.getvalue(),
        file_name="PetroLab_единая_база.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        key="export_reference_database_download",
    )
    st.caption("Экспорт включает реальные связи datasets с проектами, изображения, методы пересчёта и project-local recipes/styles.")


def render_export_reference_page() -> None:
    render_page_header(
        "Экспорт и публикация",
        "Финальный рабочий экран: собрать рисунок, подготовить supplementary-таблицу или выгрузить переносимый научный набор данных.",
        eyebrow="Публикация",
    )
    st.markdown(
        '<div class="pd-status-strip">'
        '<div class="pd-status-item"><strong>1 · Выборка</strong><span>точные analysis_id</span></div>'
        '<div class="pd-status-item"><strong>2 · Панели</strong><span>сохранённые recipes</span></div>'
        '<div class="pd-status-item"><strong>3 · Компоновка</strong><span>Figure Recipe A–F</span></div>'
        '<div class="pd-status-item"><strong>4 · Экспорт</strong><span>PNG / PDF / Excel</span></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    figure_tab, table_tab, data_tab = st.tabs(["Рисунок", "Таблицы", "Данные"])
    with figure_tab:
        _render_figure_export()
    with table_tab:
        _render_article_tables()
    with data_tab:
        _render_database_export()
