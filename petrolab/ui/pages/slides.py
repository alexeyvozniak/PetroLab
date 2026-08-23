from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from PIL import Image
from streamlit_drawable_canvas import st_canvas

from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_accessible_datasets, load_dataset_dataframe
from petrolab.measurement_registry import create_entity, list_entities
from petrolab.sample_registry import list_samples
from petrolab.slides import (
    IMAGE_TYPES,
    STORAGE_LINKED,
    attach_image_to_slide_field,
    create_slide_field,
    create_slide_marker,
    delete_slide_image,
    delete_slide_marker,
    detach_image_from_slide_field,
    field_geometry_from_corners,
    list_field_images,
    list_slide_fields,
    list_slide_images,
    list_slide_markers,
    register_linked_slide_image,
    register_managed_slide_image,
    relink_slide_original,
    render_slide_overlay,
)
from petrolab.ui.layout import render_badges, render_hint, render_page_header, render_section_header
from petrolab.ui.project_context import active_project_id


def _image_choice(images: list, key: str, label: str = "Снимок"):
    by_id = {int(image.id): image for image in images}
    selected = st.selectbox(label, list(by_id), format_func=lambda value: by_id[int(value)].title, key=key)
    return by_id[int(selected)]


def _section_label(entity: dict) -> str:
    sample = str(entity.get("sample_name") or "без Sample")
    return f"{entity['name']} · {sample}"


def _add_thin_section(project_id: int) -> None:
    sections = [item for item in list_entities(project_id) if item["kind"] == "thin_section"]
    with st.expander("Нет препарата в списке? Добавить", expanded=not sections):
        samples = list_samples(project_id)
        sample_by_id = {int(sample["id"]): sample for sample in samples}
        name = st.text_input("Название препарата", placeholder="Шлиф PG-12", key="slide_new_section_name")
        selected_sample = st.selectbox(
            "Sample (необязательно)", [None, *sample_by_id],
            format_func=lambda value: "Пока без Sample" if value is None else str(sample_by_id[int(value)]["name"]),
            key="slide_new_section_sample",
            help="Для обычного снимка достаточно названия препарата. Sample можно добавить позже.",
        )
        note = st.text_input("Заметка (необязательно)", key="slide_new_section_note")
        if st.button("Добавить препарат", type="primary", key="slide_add_section"):
            try:
                create_entity(project_id, kind="thin_section", name=name, sample_id=selected_sample, description=note)
            except Exception as exc:
                st.error(str(exc))
            else:
                st.success("Препарат добавлен. Теперь выберите его для снимка.")
                st.rerun()


def _add_image(project_id: int) -> None:
    render_section_header("1. Снимок", "Оригинал остаётся лёгким для проекта")
    st.info(
        "Для тяжёлых TIFF рекомендуется указать путь к оригиналу: ПетроЛаб создаст лёгкое превью и не будет "
        "дублировать гигабайтный файл. Переносимую копию выбирайте только если она действительно нужна на другом компьютере."
    )
    _add_thin_section(project_id)
    sections = [item for item in list_entities(project_id) if item["kind"] == "thin_section"]
    section_by_id = {int(item["id"]): item for item in sections}
    thin_section_id = st.selectbox(
        "Препарат (необязательно)", [None, *section_by_id],
        format_func=lambda value: "Не привязывать пока" if value is None else _section_label(section_by_id[int(value)]),
        key="slide_image_section",
    )
    mode = st.radio(
        "Где хранить оригинал?", ["Оставить на диске — рекомендовано", "Сохранить переносимую копию"],
        horizontal=True, key="slide_storage_mode",
        help="Первый вариант сохраняет путь и маленькое превью. Второй копирует исходный файл в данные ПетроЛаб.",
    )
    title = st.text_input("Название снимка", placeholder="Шлиф PG-12, общее поле", key="slide_image_title")
    image_type = st.selectbox("Тип снимка", IMAGE_TYPES, key="slide_image_type")
    if mode.startswith("Оставить"):
        source_path = st.text_input(
            "Полный путь к оригиналу", placeholder=r"D:\Petrology\Porja\PG-12_full.tif", key="slide_source_path",
            help="Оригинал не копируется. На другом компьютере его можно перепривязать одним действием.",
        )
        if st.button("Создать лёгкое превью", type="primary", key="slide_register_linked"):
            try:
                image = register_linked_slide_image(
                    project_id, source_path=source_path, title=title, image_type=image_type, thin_section_id=thin_section_id,
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                st.success(f"Готово: превью создано ({image.pixel_width} × {image.pixel_height} px у оригинала).")
                st.rerun()
    else:
        upload = st.file_uploader("Файл для переносимой копии", type=["png", "jpg", "jpeg", "webp", "tif", "tiff"], key="slide_master_upload")
        render_hint("Подсказка: если файл больше примерно 100 МБ, удобнее хранить оригинал отдельно и использовать первый вариант.")
        if upload is not None:
            st.caption(f"Размер файла: {upload.size / 1024 / 1024:.1f} МБ")
        if st.button("Сохранить переносимую копию", type="primary", disabled=upload is None, key="slide_register_managed"):
            try:
                image = register_managed_slide_image(
                    project_id, filename=upload.name, data=upload.getvalue(), title=title, image_type=image_type,
                    thin_section_id=thin_section_id,
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                st.success(f"Снимок добавлен. Оригинал: {image.pixel_width} × {image.pixel_height} px.")
                st.rerun()


def _coordinate_inputs(prefix: str) -> tuple[float, float]:
    st.caption("Запасной путь: координаты в процентах от левого верхнего угла.")
    x_col, y_col = st.columns(2)
    with x_col:
        x_percent = st.number_input("X, %", min_value=0.0, max_value=100.0, value=50.0, step=0.1, key=f"{prefix}_x")
    with y_col:
        y_percent = st.number_input("Y, %", min_value=0.0, max_value=100.0, value=50.0, step=0.1, key=f"{prefix}_y")
    return float(x_percent) / 100, float(y_percent) / 100


def _picker_coordinate(event: object) -> tuple[float, float] | None:
    """Read a normalized coordinate carried by an invisible Plotly hit grid."""
    if event is None:
        return None
    try:
        selection = event.get("selection", {})
    except AttributeError:
        selection = getattr(event, "selection", {}) or {}
    try:
        points = selection.get("points", [])
    except AttributeError:
        points = getattr(selection, "points", []) or []
    if not points:
        return None
    point = points[-1]
    try:
        raw = point.get("customdata")
    except AttributeError:
        raw = getattr(point, "customdata", None)
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        return float(raw[0]), float(raw[1])
    except (TypeError, ValueError):
        return None


def _slide_picker_figure(image, fields: list[dict], markers: list[dict]) -> go.Figure:
    """A click-target layer over the preview; storage stays in normalized coordinates."""
    with Image.open(Path(image.preview_path)) as source:
        preview = source.convert("RGB").copy()
    figure = go.Figure()
    figure.add_layout_image(
        dict(source=preview, x=0, y=0, sizex=100, sizey=100, xref="x", yref="y", xanchor="left", yanchor="top", sizing="stretch", layer="below")
    )
    for field in fields:
        geometry = field.get("geometry") or {}
        if {"x", "y", "width", "height"}.issubset(geometry):
            x, y = float(geometry["x"]) * 100, float(geometry["y"]) * 100
            figure.add_shape(
                type="rect", x0=x, y0=y, x1=x + float(geometry["width"]) * 100, y1=y + float(geometry["height"]) * 100,
                line={"color": "#45D6C8", "width": 2}, fillcolor="rgba(69,214,200,0.08)",
            )
            figure.add_annotation(x=x, y=y, text=str(field.get("name") or "Поле"), showarrow=False, xanchor="left", yanchor="bottom", font={"color": "#0A3331"}, bgcolor="rgba(255,255,255,.8)")
    if markers:
        figure.add_trace(go.Scatter(
            x=[float(item["x_norm"]) * 100 for item in markers], y=[float(item["y_norm"]) * 100 for item in markers],
            mode="markers+text", text=[str(item.get("label") or item.get("entity_name") or "Точка") for item in markers],
            textposition="top right", hoverinfo="skip", marker={"size": 11, "color": "#F26B4D", "line": {"color": "white", "width": 2}}, showlegend=False,
        ))
    coordinates = [(x / 100, y / 100) for x in range(0, 101, 2) for y in range(0, 101, 2)]
    figure.add_trace(go.Scattergl(
        x=[x * 100 for x, _ in coordinates], y=[y * 100 for _, y in coordinates], mode="markers",
        customdata=coordinates, hoverinfo="skip", marker={"size": 15, "color": "rgba(0,0,0,0.002)"}, showlegend=False,
    ))
    figure.update_layout(
        height=520, margin={"l": 4, "r": 4, "t": 4, "b": 4}, clickmode="event+select", dragmode="select",
        plot_bgcolor="white", paper_bgcolor="white",
    )
    figure.update_xaxes(range=[0, 100], visible=False, fixedrange=True, constrain="domain")
    figure.update_yaxes(range=[100, 0], visible=False, fixedrange=True, scaleanchor="x", scaleratio=1)
    return figure


def _pick_points(image, *, key: str, count: int, fields: list[dict] | None = None, markers: list[dict] | None = None) -> list[tuple[float, float]]:
    """Collect one or two clicks. The small target grid gives a reliable 2% precision."""
    state_key = f"{key}_picked"
    last_key = f"{key}_last_event"
    points = [tuple(value) for value in st.session_state.get(state_key, [])]
    try:
        event = st.plotly_chart(
            _slide_picker_figure(image, fields or [], markers or []), width="stretch", key=f"{key}_canvas",
            on_select="rerun", selection_mode=("points",), config={"displaylogo": False, "scrollZoom": False},
        )
    except Exception as exc:
        st.warning(f"Интерактивное превью недоступно: {exc}")
        return points
    coordinate = _picker_coordinate(event)
    if coordinate is not None and coordinate != st.session_state.get(last_key) and len(points) < count:
        points.append(coordinate)
        st.session_state[state_key] = points
        st.session_state[last_key] = coordinate
    if points:
        labels = [f"{index + 1}-й угол: {x * 100:.0f} / {y * 100:.0f} %" for index, (x, y) in enumerate(points)]
        st.caption(" · ".join(labels))
    if st.button("Сбросить выбор на изображении", key=f"{key}_reset"):
        st.session_state.pop(state_key, None)
        st.session_state.pop(last_key, None)
        st.rerun()
    return points


def _draw_field_geometry(image, *, fields: list[dict], markers: list[dict], key: str) -> dict | None:
    """Accept the last rectangle drawn on a real canvas, in preview-relative coordinates."""
    preview = render_slide_overlay(image, markers, fields)
    width, height = preview.size
    scale = min(1.0, 980 / width)
    canvas_width, canvas_height = max(1, round(width * scale)), max(1, round(height * scale))
    st.caption("Протяните мышью от одного угла к другому. Удерживайте Shift, чтобы растянуть квадрат.")
    result = st_canvas(
        fill_color="rgba(69,214,200,0.12)", stroke_width=2, stroke_color="#45D6C8", background_image=preview,
        update_streamlit=True, height=canvas_height, width=canvas_width, drawing_mode="rect", key=key,
    )
    objects = (result.json_data or {}).get("objects", [])
    if not objects:
        return None
    drawn = objects[-1]
    if str(drawn.get("type")) != "rect":
        return None
    left, top = float(drawn.get("left", 0)), float(drawn.get("top", 0))
    drawn_width = float(drawn.get("width", 0)) * float(drawn.get("scaleX", 1))
    drawn_height = float(drawn.get("height", 0)) * float(drawn.get("scaleY", 1))
    if drawn_width <= 0 or drawn_height <= 0:
        return None
    x, y = max(0.0, left / canvas_width), max(0.0, top / canvas_height)
    right, bottom = min(1.0, (left + drawn_width) / canvas_width), min(1.0, (top + drawn_height) / canvas_height)
    # Fabric keeps a Shift-drawn rectangle square. Preserve that semantic state in data too.
    shape = "square" if abs((right - x) - (bottom - y)) <= 0.01 else "rectangle"
    return field_geometry_from_corners((x, y), (right, bottom), shape=shape)


def _add_field(project_id: int, images: list) -> None:
    render_section_header("2. Поле", "Два щелчка по снимку — только прямоугольник или квадрат")
    image = _image_choice(images, "slide_field_image")
    fields = list_slide_fields(project_id, slide_image_id=image.id)
    markers = list_slide_markers(project_id, slide_image_id=image.id)
    st.caption("Поле — участок шлифа, к которому затем привязываются точки и малые BSE. Задайте его первым и вторым углом.")
    name = st.text_input("Название поля", placeholder="Поле 1 — флогопит", key="slide_field_name")
    note = st.text_input("Заметка (необязательно)", key="slide_field_note")
    geometry = _draw_field_geometry(image, fields=fields, markers=markers, key=f"slide_field_draw_{image.id}")
    if geometry is not None:
        st.success(f"Будет создан {'квадрат' if geometry['kind'] == 'square' else 'прямоугольник'}: {geometry['width'] * 100:.0f} × {geometry['height'] * 100:.0f} % снимка.")
    with st.expander("Запасной путь: два щелчка или ручные координаты"):
        shape_label = st.radio("Форма", ["Прямоугольник", "Квадрат"], horizontal=True, key="slide_field_shape")
        shape = "square" if shape_label == "Квадрат" else "rectangle"
        picked = _pick_points(image, key=f"slide_field_{image.id}", count=2, fields=fields, markers=markers)
        if len(picked) == 2:
            geometry = field_geometry_from_corners(picked[0], picked[1], shape=shape)
        manual_x, manual_y = _coordinate_inputs("slide_field")
        left, right = st.columns(2)
        with left:
            manual_width = st.number_input("Ширина, %", min_value=0.1, max_value=100.0, value=20.0, step=0.1, key="slide_field_w") / 100
        with right:
            manual_height = st.number_input("Высота, %", min_value=0.1, max_value=100.0, value=20.0, step=0.1, key="slide_field_h") / 100
        if st.checkbox("Использовать ручные координаты", key="slide_field_manual"):
            try:
                geometry = field_geometry_from_corners((manual_x, manual_y), (manual_x + float(manual_width), manual_y + float(manual_height)), shape=shape)
            except ValueError as exc:
                st.warning(str(exc))
    if st.button("Добавить поле", type="primary", key="slide_add_field"):
        try:
            if geometry is None:
                raise ValueError("Сначала задайте два угла поля на снимке или включите ручные координаты")
            create_slide_field(project_id, slide_image_id=image.id, name=name, description=note, geometry=geometry)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success("Поле добавлено.")
            st.rerun()


def _analysis_choices(project_id: int, query: str) -> tuple[list[str], dict[str, str]]:
    labels: dict[str, str] = {}
    needle = query.casefold().strip()
    for dataset in list_accessible_datasets(project_id):
        frame = load_dataset_dataframe(int(dataset["id"]), include_meta=True)
        if frame.empty or "_analysis_id" not in frame.columns:
            continue
        view = frame
        if needle:
            mask = view.astype(str).apply(lambda column: column.str.casefold().str.contains(needle, na=False)).any(axis=1)
            view = view.loc[mask]
        for _, row in view.head(250).iterrows():
            analysis_id = str(row["_analysis_id"])
            parts = [str(dataset.get("name") or f"Набор {dataset['id']}")]
            for column in ("Sample", "Образец", "Point", "Точка", "Grain", "Зерно", "Mineral", "Минерал"):
                value = row.get(column)
                if value is not None and str(value).strip() and str(value).lower() != "nan":
                    parts.append(f"{column}: {value}")
            labels[analysis_id] = " · ".join(parts)[:180]
    ids = list(labels)[:1000]
    return ids, labels


def _add_marker(project_id: int, images: list) -> None:
    render_section_header("3. Точки и кратеры", "Одна метка может связать EPMA, ЭДС и LA")
    image = _image_choice(images, "slide_marker_image")
    fields = list_slide_fields(project_id, slide_image_id=image.id)
    entities = [item for item in list_entities(project_id) if item["kind"] in {"probe_point", "la_crater", "grain"}]
    entity_by_id = {int(item["id"]): item for item in entities}
    question = st.radio(
        "Что вы отмечаете?", ["Одну физическую точку / кратер", "Только строку из таблицы"],
        horizontal=True, key="slide_marker_question",
        help="Если для одной позиции есть ЭДС и LA, выберите первую опцию и прикрепите обе строки ниже.",
    )
    entity_id = None
    if question.startswith("Одну"):
        entity_id = st.selectbox(
            "Физическая сущность (необязательно)", [None, *entity_by_id],
            format_func=lambda value: "Создам связь позже" if value is None else f"{entity_by_id[int(value)]['name']} · {entity_by_id[int(value)]['kind']}",
            key="slide_marker_entity",
        )
        render_hint("Зерно удобно использовать как общий носитель; точка зонда и LA-кратер — как его дочерние сущности в разделе «Образцы и измерения».")
    field_by_id = {int(field["id"]): field for field in fields}
    field_id = st.selectbox(
        "Поле (необязательно)", [None, *field_by_id],
        format_func=lambda value: "Без поля" if value is None else str(field_by_id[int(value)]["name"]), key="slide_marker_field",
    )
    query = st.text_input("Найти строки для привязки", placeholder="PG-12, mica, point 17…", key="slide_marker_analysis_query")
    analysis_ids, analysis_labels = _analysis_choices(project_id, query)
    saved_selection = [str(value) for value in st.session_state.get("selection_analysis_ids", [])]
    selected_analysis = st.multiselect(
        "Связанные строки анализа (можно несколько)", analysis_ids,
        default=[value for value in saved_selection if value in analysis_ids],
        format_func=lambda value: analysis_labels.get(value, value), key="slide_marker_analysis_ids",
        help="Так EDS, EPMA и LA остаются отдельными измерениями, но показываются в одном месте шлифа.",
    )
    label = st.text_input("Подпись метки", placeholder="Mica-3 / EDS-17", key="slide_marker_label")
    note = st.text_input("Заметка (необязательно)", key="slide_marker_note")
    st.caption("Нажмите место точки на снимке. Если выбрано поле, метка остаётся отдельным измерением, но получает связь с этим полем.")
    picked = _pick_points(
        image, key=f"slide_marker_{image.id}", count=1, fields=fields,
        markers=list_slide_markers(project_id, slide_image_id=image.id),
    )
    x_norm = y_norm = None
    if picked:
        x_norm, y_norm = picked[0]
    with st.expander("Ввести координаты вручную"):
        manual_x, manual_y = _coordinate_inputs("slide_marker")
        if st.checkbox("Использовать ручные координаты", key="slide_marker_manual"):
            x_norm, y_norm = manual_x, manual_y
    if st.button("Поставить метку", type="primary", key="slide_add_marker"):
        if entity_id is None and not selected_analysis:
            st.warning("Выберите физическую сущность или хотя бы одну строку анализа — иначе метка ничего не объясняет.")
            return
        try:
            if x_norm is None or y_norm is None:
                raise ValueError("Сначала нажмите место точки на снимке или включите ручные координаты")
            create_slide_marker(
                project_id, slide_image_id=image.id, field_id=field_id, entity_id=entity_id,
                analysis_ids=tuple(selected_analysis), x_norm=x_norm, y_norm=y_norm, label=label, note=note,
            )
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success("Метка добавлена. Она не объединяет и не заменяет сами измерения.")
            st.rerun()


def _map_and_manage(project_id: int, images: list) -> None:
    render_section_header("Карта", "Превью и привязки без загрузки тяжёлого оригинала")
    image = _image_choice(images, "slide_map_image")
    fields = list_slide_fields(project_id, slide_image_id=image.id)
    markers = list_slide_markers(project_id, slide_image_id=image.id)
    state = "оригинал доступен" if image.original_available else "оригинал сейчас недоступен; превью сохранено"
    tone = "success" if image.original_available else "warning"
    render_badges([(image.image_type, "neutral"), (state, tone), (f"{len(markers)} меток", "accent")])
    try:
        st.image(render_slide_overlay(image, markers, fields), caption=f"{image.title} · лёгкое рабочее превью", width="stretch")
    except Exception as exc:
        st.error(str(exc))
    if not image.original_available and image.storage_mode == STORAGE_LINKED:
        with st.expander("Перепривязать оригинал"):
            path = st.text_input("Новый полный путь", key=f"slide_relink_{image.id}")
            if st.button("Сохранить новый путь", type="primary", key=f"slide_relink_save_{image.id}"):
                try:
                    relink_slide_original(image.id, path)
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.success("Оригинал перепривязан; метки и превью не изменились.")
                    st.rerun()
    if fields:
        st.divider()
        st.markdown("#### Малый BSE для конкретного поля")
        st.caption("Выберите прямоугольное или квадратное поле на основном снимке, затем прикрепите к нему отдельный BSE-снимок. Он не будет ошибочно связан со всем шлифом.")
        field_by_id = {int(field["id"]): field for field in fields}
        field_id = st.selectbox("Поле", list(field_by_id), format_func=lambda value: str(field_by_id[int(value)]["name"]), key="slide_field_image_field")
        detailed = [candidate for candidate in images if candidate.id != image.id and candidate.image_type == "BSE"]
        linked = list_field_images(project_id, field_id=int(field_id))
        if detailed:
            by_id = {candidate.id: candidate for candidate in detailed}
            candidate_id = st.selectbox("Снимок BSE", list(by_id), format_func=lambda value: by_id[int(value)].title, key="slide_field_image_candidate")
            if st.button("Привязать к полю", type="primary", key="slide_field_image_attach"):
                try:
                    attach_image_to_slide_field(project_id, field_id=int(field_id), image_id=int(candidate_id))
                except Exception as exc:
                    st.error(str(exc))
                else:
                    st.success(f"{by_id[int(candidate_id)].title} привязан к полю {field_by_id[int(field_id)]['name']}.")
                    st.rerun()
        else:
            st.caption("Сначала добавьте отдельный BSE-снимок на вкладке «Снимок».")
        if linked:
            st.markdown("##### BSE выбранного поля")
            preview_columns = st.columns(min(3, len(linked)))
            for index, linked_image in enumerate(linked):
                with preview_columns[index % len(preview_columns)]:
                    try:
                        st.image(
                            linked_image.preview_path,
                            caption=f"{linked_image.title} → {field_by_id[int(field_id)]['name']}",
                            width="stretch",
                        )
                    except Exception:
                        st.caption(f"BSE: {linked_image.title} (превью недоступно)")
        for linked_image in linked:
            row = st.columns([3, 1])
            row[0].caption(f"{linked_image.image_type} · {linked_image.title} → {field_by_id[int(field_id)]['name']}")
            if row[1].button("Отвязать", key=f"slide_field_image_detach_{field_id}_{linked_image.id}"):
                detach_image_from_slide_field(int(field_id), int(linked_image.id))
                st.rerun()
    if markers:
        st.markdown("#### Метки")
        table = pd.DataFrame([
            {
                "Метка": item.get("label") or item.get("entity_name") or f"P{index + 1}",
                "Физический носитель": item.get("entity_name") or "—",
                "Поле": item.get("field_name") or "—",
                "Строк анализов": len(item.get("analysis_ids") or []),
                "X / Y, %": f"{float(item['x_norm']) * 100:.1f} / {float(item['y_norm']) * 100:.1f}",
            }
            for index, item in enumerate(markers)
        ])
        st.dataframe(table, width="stretch", hide_index=True)
        marker_by_id = {int(item["id"]): item for item in markers}
        remove = st.selectbox(
            "Удалить ошибочную метку", [None, *marker_by_id],
            format_func=lambda value: "Выберите метку" if value is None else (marker_by_id[int(value)].get("label") or f"Метка {value}"),
            key="slide_marker_remove",
        )
        if st.button("Удалить выбранную метку", disabled=remove is None, key="slide_delete_marker"):
            delete_slide_marker(int(remove))
            st.rerun()
    with st.expander("Удалить снимок"):
        st.warning("Будет удалено превью, переносимая копия (если была) и метки. Файл по внешнему пути не удаляется.")
        if st.button("Удалить этот снимок", key=f"slide_delete_image_{image.id}"):
            delete_slide_image(image.id)
            st.rerun()


def render_slides_page() -> None:
    render_page_header(
        "Шлифы и поля",
        "Привяжите общий снимок, поля и точки ЭДС/LA/зонда без утяжеления проекта.",
        eyebrow="Материалы",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала создайте проект — так снимки и точки не перепутаются между работами.")
        return
    render_hint("Первый раз? Идите слева направо: снимок → поле (если нужно) → метка. Все дополнительные связи можно добавить позднее.")
    images = list_slide_images(project_id)
    add_tab, field_tab, marker_tab, map_tab = st.tabs(["1 · Снимок", "2 · Поле", "3 · Метки", "Карта и BSE"])
    with add_tab:
        _add_image(project_id)
    if not images:
        with field_tab:
            st.info("Сначала добавьте снимок на первой вкладке.")
        with marker_tab:
            st.info("Сначала добавьте снимок на первой вкладке.")
        with map_tab:
            st.info("Здесь появится карта шлифа с метками.")
        return
    with field_tab:
        _add_field(project_id, images)
    with marker_tab:
        _add_marker(project_id, images)
    with map_tab:
        _map_and_manage(project_id, images)
