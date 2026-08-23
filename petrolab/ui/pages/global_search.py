from __future__ import annotations

from dataclasses import replace

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import human_point_label
from petrolab.db import link_dataset_to_project
from petrolab.search_service import (
    SCOPE_LIBRARY,
    SCOPE_PROJECT,
    SearchCatalog,
    SearchHit,
    build_search_catalog,
    query_catalog,
)
from petrolab.source_registry import SOURCE_LABEL_COLUMN, SOURCE_TABLE_COLUMN
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project, set_active_project
from petrolab.ui.smart_plot_start import seed_plot_handoff
from petrolab.ui.work_context import filter_dataframe_to_context, get_work_context


_LIBRARY_LABEL = "Во всей PetroLab"
_PROJECT_LABEL = "В текущем проекте"


def _scope_catalog(catalog: SearchCatalog, context: dict | None) -> SearchCatalog:
    if not context:
        return catalog
    dataframe = filter_dataframe_to_context(catalog.dataframe, context)
    samples = list(catalog.samples)
    datasets = list(catalog.datasets)
    entities = list(catalog.entities)
    slide_images = list(catalog.slide_images)
    images = list(catalog.images)

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
        entities = [
            item for item in entities
            if int(item.get("id") or -1) == int(thin_section_id)
            or int(item.get("parent_id") or -1) == int(thin_section_id)
        ]
        slide_images = [
            item for item in slide_images
            if int(item.get("thin_section_id") or -1) == int(thin_section_id)
        ]

    return replace(
        catalog,
        dataframe=dataframe,
        datasets=tuple(datasets),
        samples=tuple(samples),
        entities=tuple(entities),
        slide_images=tuple(slide_images),
        images=tuple(images),
    )


def _dataset_ids(dataframe: pd.DataFrame) -> list[int]:
    if dataframe.empty or "_dataset_id" not in dataframe.columns:
        return []
    return sorted({int(value) for value in pd.to_numeric(dataframe["_dataset_id"], errors="coerce").dropna().tolist()})


def _context_actions(
    result: pd.DataFrame,
    *,
    scope_label: str,
    accessible_dataset_ids: frozenset[int],
) -> None:
    if result.empty or "_analysis_id" not in result.columns:
        return
    analysis_ids = result["_analysis_id"].astype(str).drop_duplicates().tolist()
    dataset_ids = _dataset_ids(result)
    missing = [dataset_id for dataset_id in dataset_ids if dataset_id not in accessible_dataset_ids]
    context = {
        "origin": "search",
        "label": scope_label,
        "scope": scope_label,
        "query": str(st.session_state.get("global_search_query") or ""),
        "analysis_ids": analysis_ids,
        "dataset_ids": dataset_ids,
    }
    if missing:
        st.info(
            f"В результате есть {len(missing)} наборов вне текущего проекта. "
            "Подключите нужные наборы справа или в разделе «Объекты», после этого точный результат можно передать в график."
        )

    c1, c2, c3 = st.columns(3)
    disabled = bool(missing)
    if c1.button(
        "Построить график",
        type="primary",
        width="stretch",
        key="global_search_plot",
        disabled=disabled,
    ):
        seed_plot_handoff(
            st.session_state,
            dataset_ids=dataset_ids,
            analysis_ids=analysis_ids,
            context=context,
            notice="В график переданы точные результаты поиска.",
        )
        navigate("plots")
        st.rerun()
    if c2.button(
        "Таблица статьи",
        width="stretch",
        key="global_search_table",
        disabled=disabled,
    ):
        st.session_state["workflow_table_dataset_ids"] = dataset_ids
        st.session_state["workflow_table_analysis_ids"] = analysis_ids
        st.session_state["workflow_table_context"] = context
        navigate("article_tables")
        st.rerun()
    if c3.button(
        "Редактировать отбор",
        width="stretch",
        key="global_search_edit",
        disabled=disabled,
    ):
        st.session_state["workflow_edit_dataset_ids"] = dataset_ids
        st.session_state["workflow_edit_analysis_ids"] = analysis_ids
        st.session_state["workflow_edit_context"] = context
        navigate("analyses")
        st.rerun()


def _set_detail(dataset_id: int) -> None:
    st.session_state["global_search_detail_dataset_id"] = int(dataset_id)


def _link_dataset(active_project_id: int, hit: SearchHit) -> None:
    if hit.dataset_id is None:
        return
    link_dataset_to_project(
        int(active_project_id),
        int(hit.dataset_id),
        "Подключено из глобального поиска PetroLab",
    )
    st.session_state["global_search_notice"] = (
        f"Набор «{hit.title}» подключён к текущему проекту. "
        f"Исходные данные остались в проекте «{hit.project_name or 'источник'}»."
    )


def _open_workspace_hit(hit: SearchHit, *, active_project_id: int, in_current_project: bool) -> None:
    if not in_current_project and hit.project_id is not None and int(hit.project_id) != int(active_project_id):
        set_active_project(int(hit.project_id))
    if hit.kind == "sample" and hit.sample_id is not None:
        st.session_state["workspace_mode"] = "Sample"
        st.session_state["workspace_sample_id_pending"] = int(hit.sample_id)
        st.session_state["workspace_query_pending"] = hit.title
        navigate("workspace")
    elif hit.kind == "dataset" and hit.dataset_id is not None:
        st.session_state["workspace_mode"] = "Массив данных"
        st.session_state["workspace_dataset_id_pending"] = int(hit.dataset_id)
        st.session_state["workspace_query_pending"] = hit.title
        navigate("workspace")
    elif hit.thin_section_id is not None:
        st.session_state["thin_section_focus_id_pending"] = int(hit.thin_section_id)
        navigate("thin_section")
    else:
        return
    st.rerun()


def _render_hit_card(
    hit: SearchHit,
    *,
    active_project_id: int,
    accessible_dataset_ids: frozenset[int],
) -> None:
    with st.container(border=True):
        text_col, action_col = st.columns([4.5, 2])
        with text_col:
            st.markdown(f"**{hit.title}**")
            meta = []
            if hit.project_name:
                meta.append(f"Проект: {hit.project_name}")
            if hit.subtitle:
                meta.append(hit.subtitle)
            if hit.analysis_ids:
                meta.append(f"{len(hit.analysis_ids)} анализов")
            st.caption(" · ".join(meta) if meta else "Объект PetroLab")
        with action_col:
            if hit.kind == "dataset" and hit.dataset_id is not None:
                is_accessible = int(hit.dataset_id) in accessible_dataset_ids
                if st.button(
                    "Подробнее",
                    key=f"search_detail_dataset_{hit.dataset_id}",
                    width="stretch",
                ):
                    _set_detail(int(hit.dataset_id))
                    st.rerun()
                if is_accessible:
                    if st.button(
                        "Открыть",
                        key=f"search_open_dataset_{hit.dataset_id}",
                        width="stretch",
                    ):
                        _open_workspace_hit(hit, active_project_id=active_project_id, in_current_project=True)
                else:
                    if st.button(
                        "Использовать в проекте",
                        type="primary",
                        key=f"search_link_dataset_{hit.dataset_id}",
                        width="stretch",
                    ):
                        _link_dataset(active_project_id, hit)
                        _set_detail(int(hit.dataset_id))
                        st.rerun()
            else:
                if st.button(
                    "Открыть",
                    key=f"search_open_{hit.kind}_{hit.project_id}_{hit.sample_id}_{hit.image_id}_{hit.thin_section_id}_{hit.title}",
                    width="stretch",
                ):
                    _open_workspace_hit(hit, active_project_id=active_project_id, in_current_project=False)


def _render_objects(
    *,
    samples: tuple[SearchHit, ...],
    datasets: tuple[SearchHit, ...],
    entities: tuple[SearchHit, ...],
    active_project_id: int,
    accessible_dataset_ids: frozenset[int],
) -> None:
    if not any((samples, datasets, entities)):
        st.caption("Объектов и массивов по запросу нет.")
        return
    for hit in samples[:30]:
        _render_hit_card(
            hit,
            active_project_id=active_project_id,
            accessible_dataset_ids=accessible_dataset_ids,
        )
    for hit in datasets[:50]:
        _render_hit_card(
            hit,
            active_project_id=active_project_id,
            accessible_dataset_ids=accessible_dataset_ids,
        )
    for hit in entities[:30]:
        _render_hit_card(
            hit,
            active_project_id=active_project_id,
            accessible_dataset_ids=accessible_dataset_ids,
        )
    total = len(samples) + len(datasets) + len(entities)
    if total > 110:
        st.caption(f"Показаны первые 110 из {total} объектных совпадений. Уточните запрос для более точного списка.")


def _render_images(slides: tuple[SearchHit, ...], images: tuple[SearchHit, ...]) -> None:
    rows: list[dict] = []
    for hit in slides:
        rows.append({
            "Тип": "Шлиф",
            "Название": hit.title,
            "Формат": hit.subtitle,
            "Проект": hit.project_name,
            "Файл": hit.payload.get("original_filename"),
        })
    for hit in images:
        rows.append({
            "Тип": "Изображение",
            "Название": hit.title,
            "Формат": hit.subtitle,
            "Проект": hit.project_name,
            "Файл": hit.payload.get("original_filename"),
        })
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=480)
    else:
        st.caption("Изображений по запросу нет.")


def _render_sources(result: pd.DataFrame) -> None:
    if result.empty or SOURCE_LABEL_COLUMN not in result.columns:
        st.caption("Явных библиографических источников в аналитических совпадениях нет.")
        return
    grouping = [
        column for column in ("Проект", SOURCE_LABEL_COLUMN, "Минерал", "Generation")
        if column in result.columns
    ]
    if not grouping:
        return
    grouped = (
        result.groupby(grouping, dropna=False)
        .agg(Точек=("_analysis_id", "nunique"))
        .reset_index()
        .sort_values("Точек", ascending=False)
    )
    st.dataframe(grouped, width="stretch", hide_index=True, height=480)


def _dataset_detail_hit(catalog: SearchCatalog, results_datasets: tuple[SearchHit, ...]) -> SearchHit | None:
    by_id = {int(hit.dataset_id): hit for hit in results_datasets if hit.dataset_id is not None}
    requested = st.session_state.get("global_search_detail_dataset_id")
    try:
        requested_id = int(requested) if requested is not None else None
    except (TypeError, ValueError):
        requested_id = None
    if requested_id in by_id:
        return by_id[requested_id]
    if results_datasets:
        hit = results_datasets[0]
        if hit.dataset_id is not None:
            st.session_state["global_search_detail_dataset_id"] = int(hit.dataset_id)
        return hit
    return None


def _render_dataset_detail(
    hit: SearchHit | None,
    *,
    active_project_id: int,
    accessible_dataset_ids: frozenset[int],
) -> None:
    render_section_header("Контекст результата", "Источник и безопасное подключение к текущей работе")
    if hit is None or hit.dataset_id is None:
        st.caption("Выберите массив данных в результатах, чтобы увидеть его происхождение и действия.")
        return
    item = hit.payload
    st.markdown(f"### {hit.title}")
    if hit.subtitle:
        st.caption(hit.subtitle)
    render_badges([
        (str(item.get("mineral_key") or "mineral ?"), "accent"),
        (f"{int(item.get('row_count') or 0)} анализов", "neutral"),
    ])
    st.markdown("**Проект-источник**")
    st.write(hit.project_name or "Не указан")
    st.markdown("**Исходный файл**")
    st.write(str(item.get("source_filename") or "—"))
    if item.get("source_sheet"):
        st.caption(f"Лист: {item['source_sheet']}")
    if item.get("source_kind"):
        st.caption(f"Тип источника: {item['source_kind']}")

    is_accessible = int(hit.dataset_id) in accessible_dataset_ids
    if is_accessible:
        st.success("Данные уже доступны в текущем проекте.")
        if st.button("Открыть на рабочем столе", type="primary", width="stretch", key=f"detail_open_current_{hit.dataset_id}"):
            _open_workspace_hit(hit, active_project_id=active_project_id, in_current_project=True)
    else:
        st.info(
            "Подключение создаёт только ссылку на существующий набор. "
            "Химия не копируется и остаётся в проекте-источнике."
        )
        if st.button("Использовать в текущем проекте", type="primary", width="stretch", key=f"detail_link_{hit.dataset_id}"):
            _link_dataset(active_project_id, hit)
            st.rerun()

    if hit.project_id is not None and int(hit.project_id) != int(active_project_id):
        if st.button("Открыть в проекте-источнике", width="stretch", key=f"detail_source_{hit.dataset_id}"):
            _open_workspace_hit(hit, active_project_id=active_project_id, in_current_project=False)


def render_global_search_page() -> None:
    project = active_project()
    render_page_header(
        "Поиск",
        "Найдите образцы, анализы, шлифы, изображения и источники в текущем проекте или во всей локальной базе PetroLab.",
        eyebrow="Основное",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        return
    project_id = int(project["id"])
    context = get_work_context(project_id)

    notice = str(st.session_state.pop("global_search_notice", "") or "")
    if notice:
        st.success(notice)

    incoming = str(st.session_state.pop("global_search_query_pending", "") or "")
    if incoming:
        st.session_state["global_search_query"] = incoming
    pending_scope = str(st.session_state.pop("global_search_scope_pending", "") or "")
    if pending_scope:
        st.session_state["global_search_scope"] = pending_scope

    library_state = str(st.session_state.get("global_search_library_scope") or SCOPE_PROJECT)
    library_default = _LIBRARY_LABEL if library_state == SCOPE_LIBRARY else _PROJECT_LABEL
    library_choice = st.segmented_control(
        "Область базы",
        [_PROJECT_LABEL, _LIBRARY_LABEL],
        default=library_default,
        key="global_search_library_scope_selector",
        help="Поиск по всей PetroLab ничего не подключает автоматически. Нужный набор можно явно добавить в текущий проект ссылкой.",
    ) or library_default
    library_scope = SCOPE_LIBRARY if library_choice == _LIBRARY_LABEL else SCOPE_PROJECT
    st.session_state["global_search_library_scope"] = library_scope

    context_scope = "all"
    if library_scope == SCOPE_PROJECT and context:
        options = ["Весь проект", f"Здесь · {context.get('label', '')}"]
        desired = "Весь проект" if str(st.session_state.get("global_search_scope", "all")) == "all" else options[1]
        if st.session_state.get("global_search_scope_selector") not in options:
            st.session_state["global_search_scope_selector"] = desired
        selected_scope = st.segmented_control(
            "Рабочий контекст",
            options,
            default=desired,
            key="global_search_scope_selector",
        ) or desired
        context_scope = "context" if selected_scope != "Весь проект" else "all"
        st.session_state["global_search_scope"] = context_scope
    elif library_scope == SCOPE_LIBRARY:
        st.caption("Поиск читает всю локальную базу PetroLab. Подключение данных в текущий проект всегда выполняется отдельно и явно.")
    else:
        st.caption("Ищем по всему активному проекту.")

    query = st.text_input(
        "Поиск",
        key="global_search_query",
        placeholder="🔎 Sample, точка, минерал, статья, массив, изображение…",
    )
    if not query.strip():
        st.info("Введите то, что хотите найти.")
        return

    catalog = build_search_catalog(project_id, scope=library_scope)
    if context_scope == "context":
        catalog = _scope_catalog(catalog, context)
    results = query_catalog(catalog, query)
    result = results.analyses

    unique_ids = result["_analysis_id"].astype(str).nunique() if "_analysis_id" in result.columns else 0
    source_count = result[SOURCE_LABEL_COLUMN].dropna().astype(str).nunique() if SOURCE_LABEL_COLUMN in result.columns else 0
    badges = [
        (f"{unique_ids:,} анализов".replace(",", " "), "accent"),
        (f"{len(results.samples)} Sample", "neutral"),
        (f"{len(results.datasets)} массивов", "neutral"),
        (f"{len(results.entities)} объектов", "neutral"),
        (f"{len(results.slide_images) + len(results.images)} изображений", "neutral"),
        (f"{source_count} источников", "neutral"),
    ]
    if library_scope == SCOPE_LIBRARY:
        badges.insert(0, ("Вся PetroLab", "success"))
    render_badges(badges)

    if not results.has_any:
        if library_scope == SCOPE_PROJECT:
            st.info("Совпадений в текущем проекте нет. Попробуйте «Во всей PetroLab» или измените запрос.")
        else:
            st.info("Совпадений во всей базе PetroLab не найдено. Измените запрос.")
        return

    scope_label = (
        f"Поиск · {context.get('label')}"
        if context_scope == "context" and context
        else "Поиск · вся PetroLab"
        if library_scope == SCOPE_LIBRARY
        else "Поиск · весь проект"
    )
    _context_actions(
        result,
        scope_label=scope_label,
        accessible_dataset_ids=catalog.accessible_dataset_ids,
    )

    content_col, detail_col = st.columns([2.2, 1], gap="large")
    with content_col:
        analyses_tab, objects_tab, images_tab, sources_tab = st.tabs([
            "Анализы", "Объекты", "Шлифы и изображения", "Источники"
        ])
        with analyses_tab:
            if result.empty:
                st.caption("Аналитических строк по запросу нет.")
            else:
                display = result.copy()
                display.insert(0, "Точка", [human_point_label(row) for _, row in display.iterrows()])
                preferred = [column for column in (
                    "Точка", "Проект", "Минерал", "Mineral", "Method", "Метод",
                    SOURCE_LABEL_COLUMN, SOURCE_TABLE_COLUMN, "Набор", "QC уровень",
                ) if column in display.columns]
                st.dataframe(display[preferred].head(1500), width="stretch", hide_index=True, height=560)
                if len(result) > 1500:
                    st.caption(f"Показаны первые 1500 из {len(result)} строк; действия сверху используют весь результат.")

        with objects_tab:
            _render_objects(
                samples=results.samples,
                datasets=results.datasets,
                entities=results.entities,
                active_project_id=project_id,
                accessible_dataset_ids=catalog.accessible_dataset_ids,
            )

        with images_tab:
            _render_images(results.slide_images, results.images)

        with sources_tab:
            _render_sources(result)

    with detail_col:
        detail_hit = _dataset_detail_hit(catalog, results.datasets)
        _render_dataset_detail(
            detail_hit,
            active_project_id=project_id,
            accessible_dataset_ids=catalog.accessible_dataset_ids,
        )
