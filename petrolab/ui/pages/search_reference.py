from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.db import list_projects, load_dataset_dataframe
from petrolab.search import global_search
from petrolab.ui.layout import render_page_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import set_active_project
from petrolab.ui.selection_context import set_selection


def _analysis_rows(results: list[dict]) -> pd.DataFrame:
    by_dataset: dict[int, set[str]] = {}
    meta: dict[str, dict] = {}
    for result in results:
        if result.get("kind") != "analysis":
            continue
        dataset_id = int(result["dataset_id"])
        analysis_id = str(result["analysis_id"])
        by_dataset.setdefault(dataset_id, set()).add(analysis_id)
        meta[analysis_id] = result

    pieces: list[pd.DataFrame] = []
    for dataset_id, analysis_ids in by_dataset.items():
        frame = load_dataset_dataframe(dataset_id, include_meta=True)
        if frame.empty or "_analysis_id" not in frame.columns:
            continue
        view = frame[frame["_analysis_id"].astype(str).isin(analysis_ids)].copy()
        if view.empty:
            continue
        view["_analysis_id"] = view["_analysis_id"].astype(str)
        view["_dataset_id"] = dataset_id
        view["_project_name"] = view["_analysis_id"].map(lambda value: str(meta.get(str(value), {}).get("project_name") or ""))
        view["_search_title"] = view["_analysis_id"].map(lambda value: str(meta.get(str(value), {}).get("title") or value))
        view["_search_detail"] = view["_analysis_id"].map(lambda value: str(meta.get(str(value), {}).get("detail") or ""))
        pieces.append(view)
    if not pieces:
        return pd.DataFrame()
    return pd.concat(pieces, ignore_index=True, sort=False)


def _first_existing(frame: pd.DataFrame, *names: str) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _display_table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    sample = _first_existing(frame, "Sample", "Образец")
    mineral = _first_existing(frame, "Минерал", "Mineral")
    point = _first_existing(frame, "Point", "Точка")
    generation = _first_existing(frame, "Generation", "Положение")
    method = _first_existing(frame, "Method", "Метод")
    source = _first_existing(frame, "Источник", "Source")
    columns = [
        ("_analysis_id", "ID анализа"),
        (sample, "Образец"),
        (mineral, "Минерал"),
        (point, "Точка"),
        (generation, "Положение"),
        (method, "Метод"),
        (source, "Источник"),
        ("_project_name", "Проект"),
    ]
    data = {}
    for column, label in columns:
        if column and column in frame.columns:
            data[label] = frame[column]
    return pd.DataFrame(data)


def render_search_reference_page() -> None:
    render_page_header(
        "Поиск",
        "Найдите анализ, образец или изображение и соберите рабочую выборку без копирования данных.",
    )

    projects = list_projects()
    by_id = {int(row["id"]): row for row in projects}
    top = st.columns([4.5, 1.25])
    query = top[0].text_input(
        "Поиск",
        placeholder="апатит Кивгуба, 19 ТР-1, флогопит, BSE…",
        key="pd_global_search_query",
        label_visibility="collapsed",
    )
    with top[1]:
        with st.popover("Фильтры", width="stretch"):
            scope = st.radio("Область", ["Все проекты", "Выбранные"], horizontal=True, key="pd_search_scope")
            selected_projects = None
            if scope == "Выбранные":
                selected_projects = st.multiselect(
                    "Проекты",
                    list(by_id),
                    format_func=lambda value: str(by_id[int(value)]["name"]),
                    key="pd_search_projects",
                )
    if "selected_projects" not in locals():
        selected_projects = None

    if len(query.strip()) < 2:
        st.markdown(
            '<div class="pd-note-card">Введите хотя бы две буквы или цифры. Результаты появятся здесь же, без перехода на отдельную страницу.</div>',
            unsafe_allow_html=True,
        )
        return

    results = global_search(query, project_ids=selected_projects)
    analyses = [item for item in results if item.get("kind") == "analysis"]
    images = [item for item in results if item.get("kind") == "image"]
    category = st.segmented_control(
        "Тип результата",
        [f"Все · {len(results)}", f"Анализы · {len(analyses)}", f"Изображения · {len(images)}"],
        default=f"Все · {len(results)}",
        key="pd_search_category",
        label_visibility="collapsed",
    ) or f"Все · {len(results)}"
    if category.startswith("Анализы"):
        visible_results = analyses
    elif category.startswith("Изображения"):
        visible_results = images
    else:
        visible_results = results

    if not visible_results:
        st.info("Ничего не найдено.")
        return

    frame = _analysis_rows(analyses)
    left, center, right = st.columns([1.45, 3.9, 1.5], gap="small")

    with left:
        st.markdown(f'<div class="pd-panel-title">Результаты ({len(visible_results)})</div>', unsafe_allow_html=True)
        for index, result in enumerate(visible_results[:14]):
            active = st.session_state.get("pd_search_focus") == index
            with st.container(border=True):
                st.markdown(f"**{result['title']}**")
                st.caption(f"{result['detail']} · {result['project_name']}")
                if st.button("Открыть", key=f"pd_search_open_{index}", type="primary" if active else "secondary", width="stretch"):
                    st.session_state["pd_search_focus"] = index
                    set_active_project(int(result["project_id"]))
                    if result["kind"] == "analysis":
                        st.session_state["pd_search_focus_analysis"] = str(result["analysis_id"])
                    else:
                        dataset_id = result.get("dataset_id")
                        if dataset_id is not None:
                            st.session_state["workflow_image_dataset_id"] = int(dataset_id)
                        st.session_state["workflow_image_asset_id"] = int(result["asset_id"])
                        navigate("images")
                        st.rerun()
        if len(visible_results) > 14:
            st.caption(f"Показаны первые 14 из {len(visible_results)}")

    with center:
        st.markdown('<div class="pd-panel-title">Выбранные анализы</div>', unsafe_allow_html=True)
        if frame.empty:
            st.info("Для этой вкладки нет аналитических строк.")
            selected_ids: list[str] = []
        else:
            labels = {
                str(row["_analysis_id"]): str(row.get("_search_title") or row["_analysis_id"])
                for _, row in frame.iterrows()
            }
            default_ids = [str(value) for value in st.session_state.get("pd_search_selected_ids", []) if str(value) in labels]
            focus_id = str(st.session_state.get("pd_search_focus_analysis") or "")
            if focus_id in labels and focus_id not in default_ids:
                default_ids.append(focus_id)
            selected_ids = st.multiselect(
                "Рабочая выборка",
                list(labels),
                default=default_ids,
                format_func=lambda value: labels.get(str(value), str(value)),
                key="pd_search_selected_ids",
                label_visibility="collapsed",
                placeholder="Выберите один или несколько анализов",
            )
            if not selected_ids:
                selected_ids = list(labels)
                st.caption("Пока ничего не отмечено вручную: таблица показывает все найденные анализы.")
            shown = frame[frame["_analysis_id"].astype(str).isin(selected_ids)].copy()
            st.dataframe(_display_table(shown), width="stretch", hide_index=True, height=580)

    with right:
        st.markdown(f'<div class="pd-panel-title">Выбрано: {len(selected_ids) if not frame.empty else 0} анализа</div>', unsafe_allow_html=True)
        if frame.empty:
            st.caption("Выберите вкладку «Анализы», чтобы собрать выборку.")
        else:
            chosen = frame[frame["_analysis_id"].astype(str).isin(selected_ids)].copy()
            mineral_col = _first_existing(chosen, "Минерал", "Mineral")
            point_col = _first_existing(chosen, "Point", "Точка")
            method_col = _first_existing(chosen, "Method", "Метод")
            source_col = _first_existing(chosen, "Источник", "Source")
            st.caption("Что включено в выборку")
            st.markdown(f"**Проекты:** {chosen['_project_name'].nunique(dropna=True)}")
            if mineral_col:
                st.markdown(f"**Минералы:** {chosen[mineral_col].nunique(dropna=True)}")
            if point_col:
                st.markdown(f"**Точки:** {chosen[point_col].nunique(dropna=True)}")
            if method_col:
                methods = ", ".join(chosen[method_col].dropna().astype(str).drop_duplicates().head(4))
                st.markdown(f"**Методы:** {methods or '—'}")

            active_sources: set[str] | None = None
            if source_col and chosen[source_col].notna().any():
                st.divider()
                st.caption("Источники в выборке")
                active_sources = set()
                for source in chosen[source_col].dropna().astype(str).drop_duplicates().head(10):
                    count = int((chosen[source_col].astype(str) == source).sum())
                    enabled = st.toggle(f"{source} · {count}", value=True, key=f"pd_source_{hash(source)}")
                    if enabled:
                        active_sources.add(source)
                if active_sources:
                    chosen = chosen[chosen[source_col].astype(str).isin(active_sources)].copy()
                else:
                    chosen = chosen.iloc[0:0].copy()
            st.markdown(
                '<div class="pd-warning-card">Отключение источника влияет только на текущую выборку и график. Исходные анализы не удаляются.</div>',
                unsafe_allow_html=True,
            )

            if st.button("Построить график по выборке", type="primary", width="stretch", disabled=chosen.empty, key="pd_search_to_plot"):
                ids = chosen["_analysis_id"].astype(str).tolist()
                updated = set_selection(ids, origin="Поиск", mode="replace", label=query.strip())
                st.session_state["selection_analysis_ids"] = list(updated.analysis_ids)
                st.session_state["active_selection_analysis_ids"] = list(updated.analysis_ids)
                st.session_state["workflow_plot_analysis_ids"] = list(updated.analysis_ids)
                st.session_state["workflow_plot_dataset_ids"] = list(dict.fromkeys(int(value) for value in chosen["_dataset_id"].tolist()))
                if not chosen.empty:
                    first_project = next((int(result["project_id"]) for result in analyses if str(result["analysis_id"]) in set(ids)), None)
                    if first_project is not None:
                        set_active_project(first_project)
                navigate("linked_views")
                st.rerun()
