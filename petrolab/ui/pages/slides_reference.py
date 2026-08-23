from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.db import list_accessible_datasets, load_dataset_dataframe
from petrolab.measurement_registry import list_entities
from petrolab.slides import list_slide_fields, list_slide_images, list_slide_markers, render_slide_overlay
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project_id
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
    if not pieces:
        return pd.DataFrame()
    return pd.concat(pieces, ignore_index=True, sort=False)


def _first(frame: pd.DataFrame, *names: str) -> str | None:
    for name in names:
        if name in frame.columns:
            return name
    return None


def _table(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame
    mineral = _first(frame, "Минерал", "Mineral")
    point = _first(frame, "Point", "Точка")
    generation = _first(frame, "Generation", "Положение")
    method = _first(frame, "Method", "Метод")
    source = _first(frame, "Источник", "Source")
    preferred_values = [
        column for column in ("Mg#", "SiO2", "TiO2", "Al2O3", "FeO", "MgO", "Cr2O3", "NiO", "F", "Cl")
        if column in frame.columns
    ][:4]
    result = pd.DataFrame(index=frame.index)
    result["ID"] = frame["_analysis_id"].astype(str)
    if mineral:
        result["Минерал"] = frame[mineral]
    if point:
        result["Точка"] = frame[point]
    if generation:
        result["Положение"] = frame[generation]
    if method:
        result["Метод"] = frame[method]
    if preferred_values:
        result["Ключевые значения"] = frame[preferred_values].apply(
            lambda row: "   ".join(
                f"{column} {pd.to_numeric(row[column], errors='coerce'):.4g}"
                for column in preferred_values
                if pd.notna(pd.to_numeric(row[column], errors="coerce"))
            ),
            axis=1,
        )
    if source:
        result["Источник"] = frame[source]
    else:
        result["Источник"] = frame["_dataset_name"]
    return result


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


def render_slides_reference_page() -> None:
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала создайте или выберите проект.")
        return

    images = list_slide_images(project_id)
    if not images:
        st.markdown('<div class="pd-screen-title">Шлифы</div><div class="pd-screen-subtitle">Добавьте первый общий снимок, затем привяжите поля и аналитические точки.</div>', unsafe_allow_html=True)
        with st.container(border=True):
            legacy._add_image(project_id)
        return

    image_by_id = {int(image.id): image for image in images}
    default_id = int(st.session_state.get("pd_slide_image_id") or images[0].id)
    if default_id not in image_by_id:
        default_id = int(images[0].id)
    image_id = st.session_state.setdefault("pd_slide_image_id", default_id)
    image = image_by_id[int(image_id)]
    markers = list_slide_markers(project_id, slide_image_id=image.id)
    fields = list_slide_fields(project_id, slide_image_id=image.id)
    linked_ids = _analysis_ids(markers)
    frame = _analysis_frame(project_id, linked_ids)
    current_selection = set(read_selection().analysis_ids)
    selected_here = [value for value in linked_ids if value in current_selection]

    title = _section_name(project_id, image)
    top = st.columns([2.2, 3.7, 1.55, 1.1])
    with top[0]:
        st.markdown(f'<div class="pd-screen-title">{title}</div>', unsafe_allow_html=True)
        st.caption(f"{getattr(image, 'image_type', 'снимок')} · {len(markers)} меток · {len(linked_ids)} анализов")
    with top[1]:
        st.text_input("Поиск", placeholder="Поиск", key="pd_slide_search", label_visibility="collapsed")
    with top[2]:
        if st.button("Построить график", type="primary", width="stretch", disabled=not linked_ids, key="pd_slide_plot"):
            ids = selected_here or linked_ids
            updated = set_selection(ids, origin="Шлиф", mode="replace", label=title)
            st.session_state["selection_analysis_ids"] = list(updated.analysis_ids)
            st.session_state["active_selection_analysis_ids"] = list(updated.analysis_ids)
            st.session_state["workflow_plot_analysis_ids"] = list(updated.analysis_ids)
            navigate("linked_views")
            st.rerun()
    with top[3]:
        with st.popover("+ Добавить", width="stretch"):
            action = st.radio("Что добавить", ["Снимок", "Поле", "Метка"], key="pd_slide_add_kind")
            if action == "Снимок":
                legacy._add_image(project_id)
            elif action == "Поле":
                legacy._add_field(project_id, images)
            else:
                legacy._add_marker(project_id, images)

    tabs = st.tabs(["Фотографии", "Связанный шлиф", "Анализы"])

    with tabs[0]:
        left, right = st.columns([1.45, 2.55], gap="medium")
        with left:
            try:
                st.image(render_slide_overlay(image, markers, fields), width="stretch")
            except Exception as exc:
                st.error(f"Превью недоступно: {exc}")

            thumbs = st.columns(min(5, len(images)), gap="small")
            for index, candidate in enumerate(images[:5]):
                with thumbs[index % len(thumbs)]:
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
            st.caption(f"Снимок {1 + [int(value.id) for value in images].index(int(image.id))} из {len(images)}")

            with st.container(border=True):
                st.markdown('<div class="pd-panel-title">Связанный шлиф</div>', unsafe_allow_html=True)
                st.markdown(f"**{title}**")
                if fields:
                    st.caption(f"Полей: {len(fields)} · Аналитических меток: {len(markers)}")
                else:
                    st.caption("Поля пока не размечены")
                if st.button("Редактировать разметку", width="stretch", key="pd_slide_edit_map"):
                    st.session_state["pd_slide_advanced_open"] = True

        with right:
            st.markdown(f'<div class="pd-panel-title">Анализы ({len(frame)})</div>', unsafe_allow_html=True)
            if frame.empty:
                st.info("На этом снимке пока нет связанных аналитических строк.")
            else:
                table = _table(frame)
                st.dataframe(table, width="stretch", hide_index=True, height=620)
                label_map = {
                    str(row["_analysis_id"]): (
                        f"{str(row.get(_first(frame, 'Минерал', 'Mineral')) or '').strip()}"
                        f" · {str(row.get(_first(frame, 'Point', 'Точка')) or '').strip()}"
                    ).strip(" ·") or str(row["_analysis_id"])
                    for _, row in frame.iterrows()
                }
                chosen = st.multiselect(
                    "Выбранные анализы",
                    list(label_map),
                    default=[value for value in selected_here if value in label_map],
                    format_func=lambda value: label_map.get(str(value), str(value)),
                    key="pd_slide_selected_ids",
                    placeholder="Выберите анализы для общего графика",
                )
                if chosen:
                    updated = set_selection(chosen, origin="Шлиф", mode="replace", label=title)
                    st.session_state["selection_analysis_ids"] = list(updated.analysis_ids)
                    st.session_state["active_selection_analysis_ids"] = list(updated.analysis_ids)
                    selected_here = list(updated.analysis_ids)

        if frame.empty:
            selected_count = 0
        else:
            selected_count = len(selected_here)
        with st.container(border=True):
            tray = st.columns([1.1, 4.2, 1.4])
            tray[0].markdown(f"**Выбрано: {selected_count} анализов**")
            tray[0].caption("Готово для построения графика" if selected_count else "Отметьте строки выше")
            if selected_here and not frame.empty:
                mineral_col = _first(frame, "Минерал", "Mineral")
                method_col = _first(frame, "Method", "Метод")
                chips = []
                for analysis_id in selected_here[:6]:
                    row = frame[frame["_analysis_id"].astype(str) == analysis_id]
                    if row.empty:
                        continue
                    record = row.iloc[0]
                    mineral = str(record.get(mineral_col) or "Анализ") if mineral_col else "Анализ"
                    method = str(record.get(method_col) or "") if method_col else ""
                    chips.append(f'<span class="pd-chip">{mineral}{" · " + method if method else ""}</span>')
                tray[1].markdown("".join(chips), unsafe_allow_html=True)
            if tray[2].button("Построить", type="primary", width="stretch", disabled=selected_count == 0, key="pd_slide_bottom_plot"):
                navigate("linked_views")
                st.rerun()

    with tabs[1]:
        st.caption("Разметка полей, BSE и аналитических точек остаётся полностью функциональной, но вынесена из основного рабочего экрана.")
        legacy._map_and_manage(project_id, images)

    with tabs[2]:
        if frame.empty:
            st.info("Нет связанных анализов.")
        else:
            st.dataframe(_table(frame), width="stretch", hide_index=True, height=680)

    if st.session_state.pop("pd_slide_advanced_open", False):
        with st.expander("Редактирование шлифа", expanded=True):
            legacy._map_and_manage(project_id, images)
