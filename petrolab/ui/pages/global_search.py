from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import attach_work_groups
from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.generations import attach_generations
from petrolab.source_registry import SOURCE_LABEL_COLUMN, SOURCE_TABLE_COLUMN, attach_study_metadata
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


_SEARCH_COLUMNS = (
    "Sample", "Образец", "Grain", "Point", "Минерал", "Mineral",
    "Generation", "Генерация", "Method", "Метод", "Набор", "Object", "Объект",
    SOURCE_LABEL_COLUMN, SOURCE_TABLE_COLUMN,
)


def _searchable_columns(dataframe: pd.DataFrame) -> list[str]:
    return [column for column in _SEARCH_COLUMNS if column in dataframe.columns]


def _literal_search(dataframe: pd.DataFrame, query: str) -> pd.DataFrame:
    needle = str(query or "").strip()
    if not needle or dataframe.empty:
        return dataframe.iloc[0:0].copy()
    columns = _searchable_columns(dataframe)
    if not columns:
        return dataframe.iloc[0:0].copy()
    mask = pd.Series(False, index=dataframe.index, dtype=bool)
    for column in columns:
        mask |= dataframe[column].astype(str).str.contains(needle, case=False, na=False, regex=False)
    return dataframe.loc[mask].copy()


def _context_actions(result: pd.DataFrame) -> None:
    if result.empty or "_analysis_id" not in result.columns:
        return
    analysis_ids = result["_analysis_id"].astype(str).drop_duplicates().tolist()
    dataset_ids = sorted({int(value) for value in result.get("_dataset_id", pd.Series(dtype=int)).dropna().tolist()})
    context = {
        "scope": "Глобальный поиск",
        "query": str(st.session_state.get("global_search_query") or ""),
        "analysis_ids": analysis_ids,
        "dataset_ids": dataset_ids,
    }
    c1, c2, c3 = st.columns(3)
    if c1.button("Построить график", type="primary", width="stretch", key="global_search_plot"):
        st.session_state["workflow_plot_dataset_ids"] = dataset_ids
        st.session_state["workflow_plot_analysis_ids"] = analysis_ids
        st.session_state["workflow_plot_context"] = context
        st.session_state["workflow_plot_notice"] = "В график переданы результаты глобального поиска."
        navigate("plots")
        st.rerun()
    if c2.button("Таблица статьи", width="stretch", key="global_search_table"):
        st.session_state["workflow_table_dataset_ids"] = dataset_ids
        st.session_state["workflow_table_analysis_ids"] = analysis_ids
        st.session_state["workflow_table_context"] = context
        navigate("article_tables")
        st.rerun()
    if c3.button("Редактировать отбор", width="stretch", key="global_search_edit"):
        st.session_state["workflow_edit_dataset_ids"] = dataset_ids
        st.session_state["workflow_edit_analysis_ids"] = analysis_ids
        st.session_state["workflow_edit_context"] = context
        navigate("analyses")
        st.rerun()


def _open_object_actions(result: pd.DataFrame, datasets: list[dict]) -> None:
    if result.empty:
        return
    render_section_header("Открыть как объект", "Перейти из поиска к постоянному рабочему столу Sample или массива")
    c1, c2 = st.columns(2)
    samples = sorted(result["Sample"].dropna().astype(str).loc[lambda s: s.str.strip().ne("")].unique()) if "Sample" in result.columns else []
    dataset_ids = sorted({int(value) for value in result.get("_dataset_id", pd.Series(dtype=int)).dropna().tolist()})
    dataset_by_id = {int(item["id"]): item for item in datasets}

    with c1:
        if samples:
            sample = st.selectbox("Sample", samples, key="global_search_sample")
            if st.button("Открыть Sample", width="stretch", key="global_search_open_sample"):
                st.session_state["workspace_mode"] = "Sample"
                st.session_state["workspace_query_pending"] = sample
                navigate("workspace")
                st.rerun()
        else:
            st.caption("Sample среди результатов нет.")
    with c2:
        valid_dataset_ids = [value for value in dataset_ids if value in dataset_by_id]
        if valid_dataset_ids:
            selected_id = st.selectbox(
                "Массив данных",
                valid_dataset_ids,
                format_func=lambda value: f"{dataset_by_id[int(value)]['name']} · id {int(value)}",
                key="global_search_dataset",
            )
            if st.button("Открыть массив", width="stretch", key="global_search_open_dataset"):
                st.session_state["workspace_mode"] = "Массив данных"
                st.session_state["workspace_query_pending"] = str(dataset_by_id[int(selected_id)]["name"])
                navigate("workspace")
                st.rerun()
        else:
            st.caption("Отдельного массива среди результатов нет.")


def render_global_search_page() -> None:
    project = active_project()
    render_page_header(
        "Поиск",
        "Одна строка для Sample, зерна, точки, минерала, Generation, метода, массива и статьи/источника. Результат можно сразу передать в график или открыть как объект.",
        eyebrow="Основное",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        return
    project_id = int(project["id"])
    incoming = str(st.session_state.pop("global_search_query_pending", "") or "")
    if incoming:
        st.session_state["global_search_query"] = incoming
    query = st.text_input(
        "Поиск",
        key="global_search_query",
        placeholder="например: апатит; PG-15; Kandalaksha; Reguir; rim; LA-ICP-MS",
    )
    if not query.strip():
        st.info("Введите название образца, минерала, статьи, массива, поколения или точки.")
        return

    datasets = list_accessible_datasets(project_id)
    dataset_ids = [int(item["id"]) for item in datasets]
    if not dataset_ids:
        st.info("В активном проекте пока нет аналитических данных.")
        return
    dataframe = attach_study_metadata(
        attach_generations(
            attach_work_groups(load_unified_with_derived(project_id, dataset_ids))
        )
    )
    result = _literal_search(dataframe, query)
    if result.empty:
        st.info("Совпадений в аналитическом контексте проекта не найдено.")
        return

    unique_ids = result["_analysis_id"].astype(str).nunique() if "_analysis_id" in result.columns else len(result)
    samples = result["Sample"].dropna().astype(str).nunique() if "Sample" in result.columns else 0
    sources = result[SOURCE_LABEL_COLUMN].dropna().astype(str).nunique() if SOURCE_LABEL_COLUMN in result.columns else 0
    matched_datasets = result["_dataset_id"].dropna().nunique() if "_dataset_id" in result.columns else 0
    render_badges([
        (f"{unique_ids:,} точек".replace(",", " "), "accent"),
        (f"{samples} Sample", "neutral"),
        (f"{matched_datasets} массивов", "neutral"),
        (f"{sources} источников", "neutral"),
    ])
    _context_actions(result)

    all_tab, samples_tab, sources_tab, minerals_tab = st.tabs([
        "Все совпадения", "Sample", "Источники", "Минералы / Generation",
    ])
    with all_tab:
        preferred = [
            column for column in (
                "Sample", "Grain", "Point", "Минерал", "Generation", "Method",
                SOURCE_LABEL_COLUMN, SOURCE_TABLE_COLUMN, "Набор", "QC уровень", "_analysis_id",
            ) if column in result.columns
        ]
        st.dataframe(result[preferred].head(1500), width="stretch", hide_index=True, height=560)
        if len(result) > 1500:
            st.caption(f"Показаны первые 1500 из {len(result)} строк; действия сверху используют весь результат поиска.")
    with samples_tab:
        if "Sample" in result.columns:
            sample_view = (
                result.groupby("Sample", dropna=False)
                .agg(Точек=("_analysis_id", "nunique"), Массивов=("_dataset_id", "nunique"))
                .reset_index()
                .sort_values("Точек", ascending=False)
            )
            st.dataframe(sample_view, width="stretch", hide_index=True, height=480)
    with sources_tab:
        if SOURCE_LABEL_COLUMN in result.columns:
            source_view = (
                result.groupby(SOURCE_LABEL_COLUMN, dropna=False)
                .agg(Точек=("_analysis_id", "nunique"), Массивов=("_dataset_id", "nunique"))
                .reset_index()
                .sort_values("Точек", ascending=False)
            )
            st.dataframe(source_view, width="stretch", hide_index=True, height=480)
        else:
            st.caption("Явных библиографических источников в результате нет.")
    with minerals_tab:
        grouping = [column for column in ("Минерал", "Generation") if column in result.columns]
        if grouping:
            mineral_view = (
                result.groupby(grouping, dropna=False)
                .agg(Точек=("_analysis_id", "nunique"))
                .reset_index()
                .sort_values("Точек", ascending=False)
            )
            st.dataframe(mineral_view, width="stretch", hide_index=True, height=480)

    _open_object_actions(result, datasets)
