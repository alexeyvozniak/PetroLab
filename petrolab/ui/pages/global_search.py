from __future__ import annotations

from dataclasses import asdict

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import attach_work_groups
from petrolab.dataframe_utils import human_point_label
from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.generations import attach_generations
from petrolab.measurement_registry import list_entities
from petrolab.repositories.image_repository import list_image_records
from petrolab.sample_registry import list_samples
from petrolab.slides import list_slide_images
from petrolab.source_registry import SOURCE_LABEL_COLUMN, SOURCE_TABLE_COLUMN, attach_study_metadata
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project
from petrolab.ui.work_context import filter_dataframe_to_context, get_work_context


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


def _dict_matches(item: dict, query: str, keys: tuple[str, ...] | None = None) -> bool:
    needle = str(query or "").strip().casefold()
    if not needle:
        return False
    values = [item.get(key) for key in keys] if keys else [value for key, value in item.items() if not str(key).startswith("_")]
    return needle in " ".join(str(value or "") for value in values).casefold()


def _context_actions(result: pd.DataFrame, scope_label: str) -> None:
    if result.empty or "_analysis_id" not in result.columns:
        return
    analysis_ids = result["_analysis_id"].astype(str).drop_duplicates().tolist()
    dataset_ids = sorted({int(value) for value in result.get("_dataset_id", pd.Series(dtype=int)).dropna().tolist()})
    context = {
        "scope": scope_label,
        "query": str(st.session_state.get("global_search_query") or ""),
        "analysis_ids": analysis_ids,
        "dataset_ids": dataset_ids,
    }
    c1, c2, c3 = st.columns(3)
    if c1.button("Построить график", type="primary", width="stretch", key="global_search_plot"):
        st.session_state["workflow_plot_dataset_ids"] = dataset_ids
        st.session_state["workflow_plot_analysis_ids"] = analysis_ids
        st.session_state["workflow_plot_context"] = context
        st.session_state["workflow_plot_notice"] = "В график переданы результаты поиска."
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


def _scope_objects(
    *,
    context: dict | None,
    samples: list[dict],
    datasets: list[dict],
    entities: list[dict],
    slide_images: list[dict],
    images: list[dict],
) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    if not context:
        return samples, datasets, entities, slide_images, images
    sample_id = context.get("sample_id")
    sample_name = str(context.get("sample") or "").strip().casefold()
    dataset_ids = {int(value) for value in context.get("dataset_ids", [])}
    thin_section_id = context.get("thin_section_id")

    if sample_id is not None:
        samples = [item for item in samples if int(item.get("id") or -1) == int(sample_id)]
        entities = [item for item in entities if int(item.get("sample_id") or -1) == int(sample_id)]
    elif sample_name:
        samples = [item for item in samples if str(item.get("name") or "").casefold() == sample_name]
        entities = [item for item in entities if str(item.get("sample_name") or "").casefold() == sample_name]
    if dataset_ids:
        datasets = [item for item in datasets if int(item.get("id") or -1) in dataset_ids]
        images = [item for item in images if int(item.get("dataset_id") or -1) in dataset_ids]
    if thin_section_id is not None:
        entities = [item for item in entities if int(item.get("id") or -1) == int(thin_section_id) or int(item.get("parent_id") or -1) == int(thin_section_id)]
        slide_images = [item for item in slide_images if int(item.get("thin_section_id") or -1) == int(thin_section_id)]
    return samples, datasets, entities, slide_images, images


def _open_matches(samples: list[dict], datasets: list[dict], slide_images: list[dict]) -> None:
    buttons: list[tuple[str, str, dict]] = []
    if samples:
        buttons.append(("Sample", str(samples[0].get("name") or ""), samples[0]))
    if datasets:
        buttons.append(("Массив", str(datasets[0].get("name") or ""), datasets[0]))
    if slide_images:
        buttons.append(("Шлиф", str(slide_images[0].get("title") or ""), slide_images[0]))
    if not buttons:
        return
    render_section_header("Открыть найденное")
    cols = st.columns(min(3, len(buttons)))
    for index, (col, (kind, label, item)) in enumerate(zip(cols, buttons)):
        with col:
            if st.button(f"{kind} · {label}", key=f"search_open_{kind}_{index}", width="stretch"):
                if kind == "Sample":
                    st.session_state["workspace_mode"] = "Sample"
                    st.session_state["workspace_query_pending"] = label
                    navigate("workspace")
                elif kind == "Массив":
                    st.session_state["workspace_mode"] = "Массив данных"
                    st.session_state["workspace_query_pending"] = label
                    navigate("workspace")
                else:
                    if item.get("thin_section_id") is not None:
                        st.session_state["thin_section_focus_id_pending"] = int(item["thin_section_id"])
                    navigate("thin_section")
                st.rerun()


def render_global_search_page() -> None:
    project = active_project()
    render_page_header(
        "Найти",
        "Одна лупа для анализов, Sample, массивов, физических объектов и изображений. При необходимости тот же поиск можно ограничить текущим рабочим контекстом.",
        eyebrow="Основное",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        return
    project_id = int(project["id"])
    context = get_work_context(project_id)

    incoming = str(st.session_state.pop("global_search_query_pending", "") or "")
    if incoming:
        st.session_state["global_search_query"] = incoming
    pending_scope = str(st.session_state.pop("global_search_scope_pending", "") or "")
    if pending_scope:
        st.session_state["global_search_scope"] = pending_scope

    scope_mode = "all"
    if context:
        options = ["Везде", f"Здесь · {context.get('label', '')}"]
        desired = "Везде" if str(st.session_state.get("global_search_scope", "all")) == "all" else options[1]
        if st.session_state.get("global_search_scope_selector") not in options:
            st.session_state["global_search_scope_selector"] = desired
        selected_scope = st.segmented_control(
            "Область поиска",
            options,
            default=desired,
            key="global_search_scope_selector",
        ) or desired
        scope_mode = "context" if selected_scope != "Везде" else "all"
        st.session_state["global_search_scope"] = scope_mode
    else:
        st.caption("Ищем по всему активному проекту.")

    query = st.text_input(
        "Поиск",
        key="global_search_query",
        placeholder="🔎 Sample, точка, зерно, минерал, статья, массив, изображение…",
    )
    if not query.strip():
        st.info("Введите то, что хотите найти.")
        return

    datasets = list_accessible_datasets(project_id)
    dataset_ids = [int(item["id"]) for item in datasets]
    dataframe = pd.DataFrame()
    if dataset_ids:
        dataframe = attach_study_metadata(attach_generations(attach_work_groups(load_unified_with_derived(project_id, dataset_ids))))
    if scope_mode == "context":
        dataframe = filter_dataframe_to_context(dataframe, context)
    result = _literal_search(dataframe, query)

    samples = list_samples(project_id)
    entities = list_entities(project_id)
    slide_images = [asdict(item) for item in list_slide_images(project_id)]
    images = list_image_records(project_id=project_id)
    scoped_datasets = list(datasets)
    if scope_mode == "context":
        samples, scoped_datasets, entities, slide_images, images = _scope_objects(
            context=context,
            samples=samples,
            datasets=scoped_datasets,
            entities=entities,
            slide_images=slide_images,
            images=images,
        )

    sample_hits = [item for item in samples if _dict_matches(item, query, ("name", "locality", "field_lithology", "description", "notes", "aliases"))]
    dataset_hits = [item for item in scoped_datasets if _dict_matches(item, query, ("name", "mineral_key", "source_filename", "source_sheet", "source_kind"))]
    entity_hits = [item for item in entities if _dict_matches(item, query, ("name", "kind", "sample_name", "parent_name", "description"))]
    slide_hits = [item for item in slide_images if _dict_matches(item, query, ("title", "image_type", "original_filename"))]
    image_hits = [item for item in images if _dict_matches(item, query)]

    unique_ids = result["_analysis_id"].astype(str).nunique() if "_analysis_id" in result.columns else 0
    source_count = result[SOURCE_LABEL_COLUMN].dropna().astype(str).nunique() if SOURCE_LABEL_COLUMN in result.columns else 0
    render_badges([
        (f"{unique_ids:,} анализов".replace(",", " "), "accent"),
        (f"{len(sample_hits)} Sample", "neutral"),
        (f"{len(dataset_hits)} массивов", "neutral"),
        (f"{len(entity_hits)} объектов", "neutral"),
        (f"{len(slide_hits) + len(image_hits)} изображений", "neutral"),
        (f"{source_count} источников", "neutral"),
    ])

    if result.empty and not any((sample_hits, dataset_hits, entity_hits, slide_hits, image_hits)):
        st.info("Совпадений не найдено. Можно переключиться с «Здесь» на «Везде» или изменить запрос.")
        return

    _context_actions(result, f"Поиск · {context.get('label') if scope_mode == 'context' and context else 'весь проект'}")
    _open_matches(sample_hits, dataset_hits, slide_hits)

    analyses_tab, objects_tab, images_tab, sources_tab = st.tabs(["Анализы", "Объекты", "Изображения", "Источники / группы"])
    with analyses_tab:
        if result.empty:
            st.caption("Аналитических строк по запросу нет.")
        else:
            display = result.copy()
            display.insert(0, "Точка", [human_point_label(row) for _, row in display.iterrows()])
            preferred = [column for column in (
                "Точка", "Минерал", "Mineral", "Method", "Метод",
                SOURCE_LABEL_COLUMN, SOURCE_TABLE_COLUMN, "Набор", "QC уровень",
            ) if column in display.columns]
            st.dataframe(display[preferred].head(1500), width="stretch", hide_index=True, height=560)
            if len(result) > 1500:
                st.caption(f"Показаны первые 1500 из {len(result)} строк; действия сверху используют весь результат.")

    with objects_tab:
        object_rows: list[dict] = []
        for item in sample_hits:
            object_rows.append({"Тип": "Sample", "Название": item.get("name"), "Контекст": item.get("locality") or item.get("field_lithology")})
        for item in dataset_hits:
            object_rows.append({"Тип": "Массив", "Название": item.get("name"), "Контекст": item.get("mineral_key") or item.get("source_filename")})
        for item in entity_hits:
            object_rows.append({"Тип": item.get("kind"), "Название": item.get("name"), "Контекст": item.get("sample_name") or item.get("parent_name")})
        if object_rows:
            st.dataframe(pd.DataFrame(object_rows), width="stretch", hide_index=True, height=480)
        else:
            st.caption("Физических объектов и массивов по запросу нет.")

    with images_tab:
        rows = [
            {"Тип": "Шлиф", "Название": item.get("title"), "Формат": item.get("image_type"), "Файл": item.get("original_filename")}
            for item in slide_hits
        ]
        rows.extend({
            "Тип": "Изображение",
            "Название": item.get("title") or item.get("name") or item.get("filename"),
            "Формат": item.get("image_type") or item.get("kind"),
            "Файл": item.get("filename") or item.get("original_filename"),
        } for item in image_hits)
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=480)
        else:
            st.caption("Изображений по запросу нет.")

    with sources_tab:
        if not result.empty and SOURCE_LABEL_COLUMN in result.columns:
            grouping = [column for column in (SOURCE_LABEL_COLUMN, "Минерал", "Generation") if column in result.columns]
            if grouping:
                grouped = result.groupby(grouping, dropna=False).agg(Точек=("_analysis_id", "nunique")).reset_index().sort_values("Точек", ascending=False)
                st.dataframe(grouped, width="stretch", hide_index=True, height=480)
        else:
            st.caption("Явных библиографических источников в аналитических совпадениях нет.")