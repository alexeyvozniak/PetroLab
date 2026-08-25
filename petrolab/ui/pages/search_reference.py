from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.db import list_projects, load_dataset_dataframe
from petrolab.search import global_search
from petrolab.ui.layout import render_page_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import set_active_project
from petrolab.ui.reference_selection import render_manual_selection_table, render_selection_action_bar
from petrolab.ui.selection_context import read_selection, set_selection


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
    return pd.concat(pieces, ignore_index=True, sort=False) if pieces else pd.DataFrame()


def _first_existing(frame: pd.DataFrame, *names: str) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _table_columns(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return []
    sample = _first_existing(frame, "Sample", "Образец")
    grain = _first_existing(frame, "Grain", "Зерно")
    point = _first_existing(frame, "Point", "Точка")
    mineral = _first_existing(frame, "Минерал", "Mineral")
    generation = _first_existing(frame, "Generation", "Положение")
    method = _first_existing(frame, "Method", "Метод")
    source = _first_existing(frame, "Источник", "Source")
    chemistry = [
        column for column in ("SiO2", "TiO2", "Al2O3", "MgO", "FeO", "Cr2O3", "F", "Cl", "Mg#")
        if column in frame.columns
    ][:5]
    return [
        column for column in (
            sample, grain, point, mineral, generation, method, *chemistry, source, "_project_name"
        ) if column and column in frame.columns
    ]


def render_search_reference_page() -> None:
    render_page_header(
        "Поиск по всем данным",
        "Найдите анализ, образец, шлиф или изображение и соберите одну рабочую выборку без копирования данных.",
    )

    projects = list_projects()
    by_id = {int(row["id"]): row for row in projects}
    top = st.columns([4.9, 1.1])
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
            '<div class="pd-note-card">Введите хотя бы две буквы или цифры. Поиск работает по проектам, образцам, точкам, минералам, анализам и изображениям.</div>',
            unsafe_allow_html=True,
        )
        return

    results = global_search(query, project_ids=selected_projects)
    analyses = [item for item in results if item.get("kind") == "analysis"]
    images = [item for item in results if item.get("kind") == "image"]
    category = st.segmented_control(
        "Тип результата",
        [f"Все · {len(results)}", f"Анализы · {len(analyses)}", f"Шлифы и фото · {len(images)}"],
        default=f"Все · {len(results)}",
        key="pd_search_category",
        label_visibility="collapsed",
    ) or f"Все · {len(results)}"
    if category.startswith("Анализы"):
        visible_results = analyses
    elif category.startswith("Шлифы"):
        visible_results = images
    else:
        visible_results = results

    if not visible_results:
        st.info("Ничего не найдено.")
        return

    frame = _analysis_rows(analyses)
    left, center, right = st.columns([1.4, 4.35, 1.55], gap="small")

    with left:
        st.markdown(f'<div class="pd-panel-title">Результаты ({len(visible_results)})</div>', unsafe_allow_html=True)
        for index, result in enumerate(visible_results[:16]):
            active = st.session_state.get("pd_search_focus") == index
            with st.container(border=True):
                st.markdown(f"**{result['title']}**")
                st.caption(f"{result['detail']} · {result['project_name']}")
                if st.button("Открыть", key=f"pd_search_open_{index}", type="primary" if active else "secondary", width="stretch"):
                    st.session_state["pd_search_focus"] = index
                    set_active_project(int(result["project_id"]))
                    if result["kind"] == "analysis":
                        updated = set_selection(
                            [str(result["analysis_id"])],
                            origin="Поиск",
                            mode="add" if read_selection().analysis_ids else "replace",
                            label=query.strip(),
                        )
                        st.session_state["selection_analysis_ids"] = list(updated.analysis_ids)
                        st.session_state["active_selection_analysis_ids"] = list(updated.analysis_ids)
                        st.rerun()
                    dataset_id = result.get("dataset_id")
                    if dataset_id is not None:
                        st.session_state["workflow_image_dataset_id"] = int(dataset_id)
                    st.session_state["workflow_image_asset_id"] = int(result["asset_id"])
                    navigate("slides")
                    st.rerun()
        if len(visible_results) > 16:
            st.caption(f"Показаны первые 16 из {len(visible_results)}")

    chosen = frame.iloc[0:0].copy()
    with center:
        st.markdown('<div class="pd-panel-title">Анализы</div>', unsafe_allow_html=True)
        if frame.empty:
            st.info("По этому запросу нет аналитических строк.")
        else:
            chosen = render_manual_selection_table(
                frame,
                key_prefix="pd_search",
                origin="Поиск",
                columns=_table_columns(frame),
                height=600,
                max_rows=1200,
            )

    with right:
        context = read_selection()
        selection_here = frame[
            frame["_analysis_id"].astype(str).isin(set(context.analysis_ids))
        ].copy() if not frame.empty else frame
        st.markdown(f'<div class="pd-panel-title">Выбрано: {len(selection_here)} анализов</div>', unsafe_allow_html=True)
        if selection_here.empty:
            st.caption("Отметьте строки галочками в таблице.")
        else:
            mineral_col = _first_existing(selection_here, "Минерал", "Mineral")
            point_col = _first_existing(selection_here, "Point", "Точка")
            method_col = _first_existing(selection_here, "Method", "Метод")
            source_col = _first_existing(selection_here, "Источник", "Source")
            st.caption("Что включено в выборку")
            st.markdown(f"**Проекты:** {selection_here['_project_name'].nunique(dropna=True)}")
            if mineral_col:
                st.markdown(f"**Минералы:** {selection_here[mineral_col].nunique(dropna=True)}")
            if point_col:
                st.markdown(f"**Точки:** {selection_here[point_col].nunique(dropna=True)}")
            if method_col:
                methods = ", ".join(selection_here[method_col].dropna().astype(str).drop_duplicates().head(4))
                st.markdown(f"**Методы:** {methods or '—'}")

            preview = selection_here.copy()
            if source_col and selection_here[source_col].notna().any():
                st.divider()
                st.caption("Источники в выборке")
                active_sources: set[str] = set()
                for source in selection_here[source_col].dropna().astype(str).drop_duplicates().head(12):
                    count = int((selection_here[source_col].astype(str) == source).sum())
                    enabled = st.toggle(f"{source} · {count}", value=True, key=f"pd_source_{hash(source)}")
                    if enabled:
                        active_sources.add(source)
                preview = selection_here[selection_here[source_col].astype(str).isin(active_sources)].copy() if active_sources else selection_here.iloc[0:0].copy()
                st.caption(f"На график сейчас пойдёт: {len(preview)}")
            st.markdown(
                '<div class="pd-warning-card">Выключение источника влияет только на текущий просмотр и передачу на график. Исходные анализы не удаляются.</div>',
                unsafe_allow_html=True,
            )
            if st.button("Показать выбранное на графиках", type="primary", width="stretch", disabled=preview.empty, key="pd_search_to_plot"):
                ids = preview["_analysis_id"].astype(str).tolist()
                updated = set_selection(ids, origin="Поиск", mode="replace", label=query.strip())
                st.session_state["selection_analysis_ids"] = list(updated.analysis_ids)
                st.session_state["active_selection_analysis_ids"] = list(updated.analysis_ids)
                st.session_state["workflow_plot_analysis_ids"] = list(updated.analysis_ids)
                st.session_state["workflow_plot_dataset_ids"] = list(dict.fromkeys(int(value) for value in preview["_dataset_id"].tolist()))
                navigate("linked_views")
                st.rerun()

    if not frame.empty:
        render_selection_action_bar(
            frame,
            key_prefix="pd_search_bottom",
            show_images=True,
            show_statistics=True,
        )