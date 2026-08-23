from __future__ import annotations

import html

import pandas as pd
import streamlit as st

from petrolab.db import list_accessible_datasets, load_dataset_dataframe
from petrolab.measurement_registry import list_entities
from petrolab.slides import list_slide_fields, list_slide_images, list_slide_markers, render_slide_overlay
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project_id
from petrolab.ui.selection_context import clear_selection, read_selection, set_selection

from . import slides as legacy


def _light_sidebar_for_reference() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
            background:#ffffff !important; border-right:1px solid #dce3e8 !important;
        }
        [data-testid="stSidebar"] .petrolab-sidebar-brand { color:#0f7f82 !important; }
        [data-testid="stSidebar"] .petrolab-sidebar-version,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
        [data-testid="stSidebar"] .petrolab-nav-section { color:#7b8796 !important; }
        [data-testid="stSidebar"] .stButton > button { color:#425066 !important; background:transparent !important; }
        [data-testid="stSidebar"] .stButton > button:hover { background:#f3f7f8 !important; }
        [data-testid="stSidebar"] .stButton > button[kind="primary"],
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
            color:#0f6e71 !important; background:#e9f5f4 !important;
            border-color:#c4dfdf !important; border-left:3px solid #0f7f82 !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background:#ffffff !important; border-color:#d5dde3 !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] span,
        [data-testid="stSidebar"] [data-baseweb="select"] svg { color:#334155 !important; fill:#334155 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


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
    result["Источник"] = frame[source] if source else frame["_dataset_name"]
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


def _render_editor(project_id: int, images: list, editor: str) -> None:
    if not editor:
        return
    labels = {"Снимок": "Добавить снимок", "Поле": "Добавить поле", "Метка": "Добавить метку", "Разметка": "Редактирование шлифа"}
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
    _light_sidebar_for_reference()
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
    context = read_selection()
    current_selection = set(context.analysis_ids)
    selected_here = [value for value in linked_ids if value in current_selection]

    title = _section_name(project_id, image)
    safe_title = html.escape(title)
    top = st.columns([2.2, 3.7, 1.55, 1.1])
    with top[0]:
        st.markdown(f'<div class="pd-screen-title">{safe_title}</div>', unsafe_allow_html=True)
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
            if st.button("Снимок", width="stretch", key="pd_slide_add_image"):
                st.session_state["pd_slide_editor"] = "Снимок"
            if st.button("Поле", width="stretch", key="pd_slide_add_field"):
                st.session_state["pd_slide_editor"] = "Поле"
            if st.button("Метка", width="stretch", key="pd_slide_add_marker"):
                st.session_state["pd_slide_editor"] = "Метка"

    tabs = st.tabs(["Фотографии", "Связанный шлиф", "Анализы"])

    with tabs[0]:
        left, right = st.columns([1.45, 2.55], gap="medium")
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
                st.caption(f"Полей: {len(fields)} · Аналитических меток: {len(markers)}" if fields else f"Аналитических меток: {len(markers)}")
                if st.button("Редактировать разметку", width="stretch", key="pd_slide_edit_map"):
                    st.session_state["pd_slide_editor"] = "Разметка"

        with right:
            st.markdown(f'<div class="pd-panel-title">Анализы ({len(frame)})</div>', unsafe_allow_html=True)
            if frame.empty:
                st.info("На этом снимке пока нет связанных аналитических строк.")
            else:
                st.dataframe(_table(frame), width="stretch", hide_index=True, height=570)
                mineral_col = _first(frame, "Минерал", "Mineral")
                point_col = _first(frame, "Point", "Точка")
                label_map: dict[str, str] = {}
                for _, row in frame.iterrows():
                    mineral = str(row.get(mineral_col) or "").strip() if mineral_col else ""
                    point = str(row.get(point_col) or "").strip() if point_col else ""
                    label_map[str(row["_analysis_id"])] = " · ".join(value for value in (mineral, point) if value) or str(row["_analysis_id"])

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
                elif context.origin == "Шлиф" and context.analysis_ids:
                    clear_selection()
                    st.session_state["selection_analysis_ids"] = []
                    st.session_state["active_selection_analysis_ids"] = []
                    selected_here = []

        selected_count = len(selected_here) if not frame.empty else 0
        with st.container(border=True):
            tray = st.columns([1.1, 4.2, 1.4])
            tray[0].markdown(f"**Выбрано: {selected_count} анализов**")
            tray[0].caption("Готово для построения графика" if selected_count else "Отметьте строки выше")
            if selected_here and not frame.empty:
                mineral_col = _first(frame, "Минерал", "Mineral")
                method_col = _first(frame, "Method", "Метод")
                chips: list[str] = []
                for analysis_id in selected_here[:6]:
                    row = frame[frame["_analysis_id"].astype(str) == analysis_id]
                    if row.empty:
                        continue
                    record = row.iloc[0]
                    mineral = str(record.get(mineral_col) or "Анализ") if mineral_col else "Анализ"
                    method = str(record.get(method_col) or "") if method_col else ""
                    chip_text = html.escape(mineral + (" · " + method if method else ""))
                    chips.append(f'<span class="pd-chip">{chip_text}</span>')
                tray[1].markdown("".join(chips), unsafe_allow_html=True)
            if tray[2].button("Построить", type="primary", width="stretch", disabled=selected_count == 0, key="pd_slide_bottom_plot"):
                navigate("linked_views")
                st.rerun()

    with tabs[1]:
        st.caption("Поля, BSE и аналитические метки остаются отдельными сущностями и редактируются без изменения самих измерений.")
        legacy._map_and_manage(project_id, images)

    with tabs[2]:
        if frame.empty:
            st.info("Нет связанных анализов.")
        else:
            st.dataframe(_table(frame), width="stretch", hide_index=True, height=680)

    _render_editor(project_id, images, str(st.session_state.get("pd_slide_editor") or ""))
