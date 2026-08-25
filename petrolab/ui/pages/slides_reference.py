from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from petrolab.db import list_accessible_datasets, load_dataset_dataframe
from petrolab.measurement_registry import list_entities
from petrolab.slides import list_slide_fields, list_slide_images, list_slide_markers, render_slide_overlay
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project_id
from petrolab.ui.reference_selection import render_manual_selection_table, render_selection_action_bar
from petrolab.ui.selection_context import read_selection, set_selection

from . import slides as legacy


def _analysis_frame(project_id: int, analysis_ids: list[str]) -> pd.DataFrame:
    wanted = {str(value) for value in analysis_ids if str(value)}
    if not wanted:
        return pd.DataFrame()
    pieces: list[pd.DataFrame] = []
    for dataset in list_accessible_datasets(project_id):
        frame = load_dataset_dataframe(int(dataset["id"]), include_meta=True)
        if frame.empty or "_analysis_id" not in frame.columns:
            continue
        view = frame[frame["_analysis_id"].astype(str).isin(wanted)].copy()
        if view.empty:
            continue
        view["_analysis_id"] = view["_analysis_id"].astype(str)
        view["_dataset_name"] = str(dataset.get("name") or f"Набор {dataset['id']}")
        view["_dataset_id"] = int(dataset["id"])
        pieces.append(view)
    return pd.concat(pieces, ignore_index=True, sort=False) if pieces else pd.DataFrame()


def _first(frame: pd.DataFrame, *names: str) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _table_columns(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return []
    mineral = _first(frame, "Минерал", "Mineral")
    point = _first(frame, "Point", "Точка")
    grain = _first(frame, "Grain", "Зерно")
    generation = _first(frame, "Generation", "Положение")
    method = _first(frame, "Method", "Метод")
    source = _first(frame, "Источник", "Source")
    chemistry = [
        column for column in ("SiO2", "TiO2", "Al2O3", "MgO", "FeO", "Cr2O3", "Mg#", "F", "Cl")
        if column in frame.columns
    ][:5]
    return [
        column for column in (grain, point, mineral, generation, method, *chemistry, source, "_dataset_name")
        if column and column in frame.columns
    ]


def _section_name(project_id: int, image) -> str:
    thin_section_id = getattr(image, "thin_section_id", None)
    if thin_section_id is None:
        return str(getattr(image, "title", "Шлиф"))
    for entity in list_entities(project_id):
        try:
            if int(entity.get("id")) == int(thin_section_id):
                return str(entity.get("sample_name") or entity.get("name") or getattr(image, "title", "Шлиф"))
        except (TypeError, ValueError):
            continue
    return str(getattr(image, "title", "Шлиф"))


def _analysis_ids(markers: list[dict]) -> list[str]:
    return list(dict.fromkeys(
        str(analysis_id)
        for marker in markers
        for analysis_id in marker.get("analysis_ids") or []
        if str(analysis_id)
    ))


def _render_editor(project_id: int, images: list, editor: str) -> None:
    if not editor:
        return
    labels = {
        "Снимок": "Добавить снимок",
        "Поле": "Добавить поле",
        "Метка": "Добавить метку",
        "Разметка": "Редактирование шлифа",
    }
    with st.expander(labels.get(editor, editor), expanded=True):
        if editor == "Снимок":
            legacy._add_image(project_id)
        elif editor == "Поле":
            legacy._add_field(project_id, images)
        elif editor == "Метка":
            legacy._add_marker(project_id, images)
        elif editor == "Разметка":
            legacy._map_and_manage(project_id, images)


def render_slides_reference_page() -> None:
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала создайте или выберите проект.")
        return

    images = list_slide_images(project_id)
    if not images:
        st.markdown(
            '<div class="pd-screen-title">Шлифы</div>'
            '<div class="pd-screen-subtitle">Добавьте первый общий снимок, затем привяжите поля и аналитические точки.</div>',
            unsafe_allow_html=True,
        )
        with st.container(border=True):
            legacy._add_image(project_id)
        return

    image_by_id = {int(image.id): image for image in images}
    raw_image_id = st.session_state.get("pd_slide_image_id")
    try:
        current_id = int(raw_image_id) if raw_image_id is not None else int(images[0].id)
    except (TypeError, ValueError):
        current_id = int(images[0].id)
    if current_id not in image_by_id:
        current_id = int(images[0].id)
    st.session_state["pd_slide_image_id"] = current_id
    image = image_by_id[current_id]

    markers = list_slide_markers(project_id, slide_image_id=image.id)
    fields = list_slide_fields(project_id, slide_image_id=image.id)
    linked_ids = _analysis_ids(markers)
    frame = _analysis_frame(project_id, linked_ids)

    title = _section_name(project_id, image)
    safe_title = html.escape(title)
    top = st.columns([2.15, 3.85, 1.45, 1.05])
    with top[0]:
        st.markdown(f'<div class="pd-screen-title">{safe_title}</div>', unsafe_allow_html=True)
        st.caption(f"{getattr(image, 'image_type', 'снимок')} · {len(markers)} меток · {len(linked_ids)} анализов")
    with top[1]:
        st.text_input("Поиск", placeholder="Поиск по точкам и анализам", key="pd_slide_search", label_visibility="collapsed")
    with top[2]:
        if st.button("Показать на графиках", type="primary", width="stretch", disabled=not read_selection().analysis_ids and not linked_ids, key="pd_slide_plot"):
            ids = list(read_selection().analysis_ids) or linked_ids
            updated = set_selection(ids, origin="Шлиф", mode="replace", label=title)
            st.session_state["selection_analysis_ids"] = list(updated.analysis_ids)
            st.session_state["active_selection_analysis_ids"] = list(updated.analysis_ids)
            st.session_state["workflow_plot_analysis_ids"] = list(updated.analysis_ids)
            navigate("linked_views")
            st.rerun()
    with top[3]:
        with st.popover("+ Добавить", width="stretch"):
            if st.button("Снимок", width="stretch", key="pd_slide_add_image"):
                st.session_state["pd_slide_editor"] = "Снимок"
            if st.button("Поле", width="stretch", key="pd_slide_add_field"):
                st.session_state["pd_slide_editor"] = "Поле"
            if st.button("Метка", width="stretch", key="pd_slide_add_marker"):
                st.session_state["pd_slide_editor"] = "Метка"

    tabs = st.tabs(["Шлиф", "Анализы", "Разметка"])

    with tabs[0]:
        left, right = st.columns([1.55, 2.65], gap="medium")
        with left:
            try:
                st.image(render_slide_overlay(image, markers, fields), width="stretch")
            except Exception as exc:
                st.error(f"Превью недоступно: {exc}")

            thumb_count = min(5, len(images))
            thumbs = st.columns(thumb_count, gap="small")
            for index, candidate in enumerate(images[:5]):
                with thumbs[index % thumb_count]:
                    try:
                        st.image(candidate.preview_path, width="stretch")
                    except Exception:
                        st.caption(candidate.title)
                    if st.button(
                        "Открыть",
                        key=f"pd_slide_thumb_{candidate.id}",
                        type="primary" if int(candidate.id) == int(image.id) else "secondary",
                        width="stretch",
                    ):
                        st.session_state["pd_slide_image_id"] = int(candidate.id)
                        st.rerun()
            current_index = [int(value.id) for value in images].index(int(image.id)) + 1
            st.caption(f"Снимок {current_index} из {len(images)}")

            with st.container(border=True):
                st.markdown('<div class="pd-panel-title">Связанный шлиф</div>', unsafe_allow_html=True)
                st.markdown(f"**{safe_title}**")
                st.caption(f"Полей: {len(fields)} · Аналитических меток: {len(markers)}")
                if st.button("Редактировать разметку", width="stretch", key="pd_slide_edit_map"):
                    st.session_state["pd_slide_editor"] = "Разметка"

        with right:
            st.markdown(f'<div class="pd-panel-title">Анализы ({len(frame)})</div>', unsafe_allow_html=True)
            if frame.empty:
                st.info("На этом снимке пока нет связанных аналитических строк.")
            else:
                render_manual_selection_table(
                    frame,
                    key_prefix="pd_slide_main",
                    origin="Шлиф",
                    columns=_table_columns(frame),
                    height=570,
                    max_rows=1000,
                )

        if not frame.empty:
            render_selection_action_bar(
                frame,
                key_prefix="pd_slide_bottom",
                project_id=project_id,
                show_images=False,
                show_statistics=True,
            )

    with tabs[1]:
        if frame.empty:
            st.info("Нет связанных анализов.")
        else:
            render_manual_selection_table(
                frame,
                key_prefix="pd_slide_analysis_tab",
                origin="Шлиф",
                columns=_table_columns(frame),
                height=680,
                max_rows=1500,
            )
            render_selection_action_bar(
                frame,
                key_prefix="pd_slide_analysis_bottom",
                project_id=project_id,
                show_images=False,
                show_statistics=True,
            )

    with tabs[2]:
        st.caption("Поля, BSE и аналитические метки остаются отдельными сущностями. Разметка не меняет сами измерения.")
        legacy._map_and_manage(project_id, images)

    _render_editor(project_id, images, str(st.session_state.get("pd_slide_editor") or ""))