from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw

try:
    from streamlit_image_coordinates import streamlit_image_coordinates
except ImportError:  # pragma: no cover - guarded UI fallback
    streamlit_image_coordinates = None

from petrolab.db import connect, list_accessible_datasets, load_dataset_dataframe
from petrolab.linked_petrography import (
    analysis_ids_for_marker,
    dataset_ids_for_analysis_ids,
    marker_ids_for_selection,
    nearest_marker_id,
)
from petrolab.measurement_registry import create_entity, list_entities
from petrolab.sample_registry import list_samples
from petrolab.slides import (
    IMAGE_TYPES,
    create_slide_field,
    create_slide_marker,
    delete_slide_marker,
    list_slide_fields,
    list_slide_images,
    list_slide_markers,
    register_managed_slide_image,
)
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project
from petrolab.ui.selection_context import read_selection, set_selection
from petrolab.ui.smart_plot_start import seed_selection_plot_handoff
from petrolab.ui.work_context import set_work_context


QUICK_IMAGE_TYPES = ("PPL", "XPL", *IMAGE_TYPES)


def _go(route: str) -> None:
    navigate(route)
    st.rerun()


def _delete_field(field_id: int) -> None:
    with connect() as con:
        con.execute("DELETE FROM slide_fields WHERE id=?", (int(field_id),))
        con.commit()


def _event_point(value: dict | None) -> tuple[float, float] | None:
    if not value:
        return None
    width = float(value.get("width") or 0)
    height = float(value.get("height") or 0)
    if width <= 0 or height <= 0 or "x" not in value or "y" not in value:
        return None
    return max(0.0, min(1.0, float(value["x"]) / width)), max(0.0, min(1.0, float(value["y"]) / height))


def _event_rectangle(value: dict | None) -> dict | None:
    if not value:
        return None
    width = float(value.get("width") or 0)
    height = float(value.get("height") or 0)
    required = {"x1", "y1", "x2", "y2"}
    if width <= 0 or height <= 0 or not required.issubset(value):
        return None
    x1, x2 = sorted((float(value["x1"]) / width, float(value["x2"]) / width))
    y1, y2 = sorted((float(value["y1"]) / height, float(value["y2"]) / height))
    x1, x2 = max(0.0, x1), min(1.0, x2)
    y1, y2 = max(0.0, y1), min(1.0, y2)
    if x2 <= x1 or y2 <= y1:
        return None
    return {"kind": "region", "x": x1, "y": y1, "width": x2 - x1, "height": y2 - y1}


def _analysis_choices(project_id: int, query: str) -> tuple[list[str], dict[str, str]]:
    labels: dict[str, str] = {}
    needle = str(query or "").strip().casefold()
    for dataset in list_accessible_datasets(project_id):
        frame = load_dataset_dataframe(int(dataset["id"]), include_meta=True)
        if frame.empty or "_analysis_id" not in frame.columns:
            continue
        view = frame
        if needle:
            mask = view.astype(str).apply(lambda column: column.str.casefold().str.contains(needle, na=False, regex=False)).any(axis=1)
            view = view.loc[mask]
        for _, row in view.head(250).iterrows():
            analysis_id = str(row["_analysis_id"])
            parts = [str(dataset.get("name") or f"Набор {dataset['id']}")]
            for column in ("Sample", "Образец", "Point", "Точка", "Grain", "Зерно", "Mineral", "Минерал", "Generation"):
                value = row.get(column)
                if value is not None and str(value).strip() and str(value).lower() != "nan":
                    parts.append(f"{column}: {value}")
            labels[analysis_id] = " · ".join(parts)[:200]
    ids = list(labels)[:1000]
    return ids, labels


def _field_kind(field: dict) -> str:
    geometry = field.get("geometry") or {}
    return str(geometry.get("kind") or ("region" if {"x", "y", "width", "height"}.issubset(geometry) else "field"))


def _render_overlay(
    image,
    markers: list[dict],
    fields: list[dict],
    *,
    show_points: bool,
    show_regions: bool,
    show_grains: bool,
    selected_marker_ids: tuple[int, ...] = (),
    pending_vertices: list[tuple[float, float]] | None = None,
) -> Image.Image:
    preview = Path(image.preview_path)
    with Image.open(preview) as source:
        canvas = source.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size
    selected = set(int(value) for value in selected_marker_ids)

    for field in fields:
        geometry = field.get("geometry") or {}
        kind = _field_kind(field)
        if kind == "grain" and not show_grains:
            continue
        if kind != "grain" and not show_regions:
            continue
        if kind == "grain" and geometry.get("vertices"):
            points = [(float(x) * width, float(y) * height) for x, y in geometry["vertices"]]
            if len(points) >= 2:
                draw.line(points + [points[0]], fill="#4BA3FF", width=max(2, width // 700))
                draw.text(points[0], str(field.get("name") or "Зерно"), fill="#163E63", stroke_width=2, stroke_fill="white")
        elif {"x", "y", "width", "height"}.issubset(geometry):
            x = float(geometry["x"]) * width
            y = float(geometry["y"]) * height
            right = x + float(geometry["width"]) * width
            bottom = y + float(geometry["height"]) * height
            draw.rectangle((x, y, right, bottom), outline="#45D6C8", width=max(2, width // 700))
            draw.text((x + 4, y + 4), str(field.get("name") or "Область"), fill="#0A3331", stroke_width=2, stroke_fill="white")

    if show_points:
        radius = max(5, min(16, width // 140))
        for index, marker in enumerate(markers, 1):
            marker_id = int(marker["id"])
            is_selected = marker_id in selected
            marker_radius = radius + (4 if is_selected else 0)
            x = float(marker["x_norm"]) * width
            y = float(marker["y_norm"]) * height
            if is_selected:
                outer = marker_radius + max(3, width // 500)
                draw.ellipse((x - outer, y - outer, x + outer, y + outer), outline="#174EA6", width=max(4, width // 450))
            draw.ellipse(
                (x - marker_radius, y - marker_radius, x + marker_radius, y + marker_radius),
                fill="#F26B4D",
                outline="#174EA6" if is_selected else "white",
                width=4 if is_selected else 2,
            )
            label = str(marker.get("label") or marker.get("entity_name") or f"P{index}")
            draw.text((x + marker_radius + 3, y - marker_radius), label, fill="#452019", stroke_width=2, stroke_fill="white")

    vertices = pending_vertices or []
    if vertices:
        points = [(float(x) * width, float(y) * height) for x, y in vertices]
        if len(points) >= 2:
            draw.line(points, fill="#4BA3FF", width=max(2, width // 700))
        for x, y in points:
            r = max(4, width // 220)
            draw.ellipse((x - r, y - r, x + r, y + r), fill="#4BA3FF", outline="white", width=2)
    return canvas


def _section_label(entity: dict) -> str:
    sample = str(entity.get("sample_name") or "без Sample")
    return f"{entity['name']} · {sample}"


def _create_section(project_id: int) -> None:
    samples = list_samples(project_id)
    sample_by_id = {int(sample["id"]): sample for sample in samples}
    with st.expander("＋ Новый шлиф"):
        name = st.text_input("Название шлифа", placeholder="KIV-2-1", key="thin_new_name")
        sample_id = st.selectbox(
            "Sample",
            [None, *sample_by_id],
            format_func=lambda value: "Пока без Sample" if value is None else str(sample_by_id[int(value)]["name"]),
            key="thin_new_sample",
        )
        note = st.text_input("Заметка", key="thin_new_note")
        if st.button("Создать шлиф", type="primary", key="thin_create_section"):
            try:
                create_entity(project_id, kind="thin_section", name=name, sample_id=sample_id, description=note)
            except Exception as exc:
                st.error(str(exc))
            else:
                st.rerun()


def _quick_upload(project_id: int, section_id: int) -> None:
    with st.expander("＋ Добавить снимок"):
        image_type = st.selectbox("Тип", QUICK_IMAGE_TYPES, key="thin_upload_type")
        uploads = st.file_uploader(
            "Изображение",
            type=["png", "jpg", "jpeg", "webp", "tif", "tiff"],
            accept_multiple_files=True,
            key="thin_upload_files",
        )
        if uploads:
            total_mb = sum(int(upload.size) for upload in uploads) / 1024 / 1024
            st.caption(f"{len(uploads)} файл(а) · {total_mb:.1f} МБ. Для очень больших TIFF удобнее расширенный режим с хранением оригинала на диске.")
        if st.button("Добавить к шлифу", type="primary", disabled=not uploads, key="thin_upload_save"):
            for upload in uploads or []:
                register_managed_slide_image(
                    project_id,
                    filename=upload.name,
                    data=upload.getvalue(),
                    title=Path(upload.name).stem,
                    image_type=image_type,
                    thin_section_id=section_id,
                )
            st.success("Снимки добавлены.")
            st.rerun()


def _local_search(markers: list[dict], fields: list[dict], query: str) -> tuple[list[dict], list[dict]]:
    needle = str(query or "").strip().casefold()
    if not needle:
        return markers, fields
    marker_result = []
    for marker in markers:
        haystack = " ".join(str(marker.get(key) or "") for key in ("label", "note", "entity_name", "entity_kind", "field_name"))
        haystack += " " + " ".join(str(value) for value in marker.get("analysis_ids", []))
        if needle in haystack.casefold():
            marker_result.append(marker)
    field_result = [
        field for field in fields
        if needle in f"{field.get('name', '')} {field.get('description', '')} {_field_kind(field)}".casefold()
    ]
    return marker_result, field_result


def _select_marker(project_id: int, markers: list[dict], marker_id: int, *, image_title: str) -> bool:
    analysis_ids = analysis_ids_for_marker(markers, int(marker_id))
    if not analysis_ids:
        st.warning("Эта физическая точка пока не связана ни с одним анализом.")
        return False
    marker = next((item for item in markers if int(item["id"]) == int(marker_id)), None)
    label = str((marker or {}).get("label") or (marker or {}).get("entity_name") or f"Точка {marker_id}")
    set_selection(
        analysis_ids,
        origin=f"Шлиф · {image_title} · {label}",
        mode="replace",
        label=label,
    )
    return True


def _open_marker_in_plots(project_id: int, markers: list[dict], marker_id: int, *, image_title: str) -> None:
    if not _select_marker(project_id, markers, marker_id, image_title=image_title):
        return
    context = read_selection()
    dataset_ids = dataset_ids_for_analysis_ids(project_id, context.analysis_ids)
    seed_selection_plot_handoff(
        st.session_state,
        dataset_ids=dataset_ids,
        analysis_ids=context.analysis_ids,
        origin=context.origin or "Шлиф",
    )
    navigate("plots")
    st.rerun()


def _annotation_panel(project_id: int, image, markers: list[dict], fields: list[dict]) -> None:
    render_section_header("Разметка", "Просмотр — выбрать существующую физическую точку; разметка — добавить новую")
    if streamlit_image_coordinates is None:
        st.error("Компонент разметки не установлен. Установите зависимости из requirements.txt или откройте расширенный режим.")
        return

    selection = read_selection()
    selection_marker_ids = marker_ids_for_selection(markers, selection.analysis_ids)
    if selection.analysis_ids:
        render_badges([
            (f"Selection · {selection.count}", "accent"),
            (f"на этом снимке · {len(selection_marker_ids)} точ.", "success" if selection_marker_ids else "neutral"),
        ])

    search_col, everywhere_col = st.columns([5, 1])
    with search_col:
        local_query = st.text_input(
            "Найти в шлифе",
            key=f"thin_local_search_{image.thin_section_id}",
            placeholder="🔎 Найти в этом шлифе: точку, зерно, подпись…",
            label_visibility="collapsed",
        )
    with everywhere_col:
        if st.button("Везде", key=f"thin_search_everywhere_{image.id}", width="stretch", help="Искать тот же запрос во всём проекте"):
            st.session_state["global_search_query_pending"] = str(local_query or "").strip()
            st.session_state["global_search_scope_pending"] = "all"
            _go("search")

    visible_markers, visible_fields = _local_search(markers, fields, local_query)
    if local_query:
        render_badges([(f"точек · {len(visible_markers)}", "accent"), (f"областей/контуров · {len(visible_fields)}", "neutral")])

    layer_cols = st.columns(3)
    show_points = layer_cols[0].checkbox("Точки", value=True, key=f"thin_layer_points_{image.id}")
    show_regions = layer_cols[1].checkbox("Области", value=True, key=f"thin_layer_regions_{image.id}")
    show_grains = layer_cols[2].checkbox("Контуры зерен", value=True, key=f"thin_layer_grains_{image.id}")
    mode = st.segmented_control(
        "Режим",
        ["Просмотр", "Точка анализа", "Область", "Контур зерна"],
        default="Точка анализа",
        key=f"thin_mode_{image.id}",
    ) or "Просмотр"

    polygon_key = f"thin_polygon_{image.id}"
    vertices = list(st.session_state.get(polygon_key, []))
    visible_selection_marker_ids = marker_ids_for_selection(visible_markers, selection.analysis_ids)
    overlay = _render_overlay(
        image,
        visible_markers,
        visible_fields,
        show_points=show_points,
        show_regions=show_regions,
        show_grains=show_grains,
        selected_marker_ids=visible_selection_marker_ids,
        pending_vertices=vertices if mode == "Контур зерна" else None,
    )

    if mode == "Просмотр":
        if not show_points or not visible_markers:
            st.image(overlay, width="stretch")
            st.caption("Включите слой «Точки», чтобы выбирать физические отметки прямо на снимке.")
            return
        event = streamlit_image_coordinates(
            overlay,
            use_column_width="always",
            key=f"thin_view_canvas_{image.id}",
        )
        token = int((event or {}).get("unix_time") or 0)
        state_key = f"thin_view_event_{image.id}"
        if token and token != int(st.session_state.get(state_key, 0)):
            st.session_state[state_key] = token
            point = _event_point(event)
            if point:
                ratio = float(image.pixel_height or 1) / float(image.pixel_width or 1)
                marker_id = nearest_marker_id(
                    visible_markers,
                    x_norm=float(point[0]),
                    y_norm=float(point[1]),
                    aspect_ratio=ratio,
                )
                if marker_id is not None and _select_marker(project_id, markers, marker_id, image_title=str(image.title)):
                    st.rerun()
        st.caption("Кликните по существующей отметке: Selection станет всеми измерениями этой физической позиции (например EPMA + LA-ICP-MS).")
        return

    if mode == "Область":
        event = streamlit_image_coordinates(
            overlay,
            use_column_width="always",
            click_and_drag=True,
            key=f"thin_region_canvas_{image.id}",
        )
        token = int((event or {}).get("unix_time") or 0)
        state_key = f"thin_region_event_{image.id}"
        if token and token != int(st.session_state.get(state_key, 0)):
            geometry = _event_rectangle(event)
            st.session_state[state_key] = token
            if geometry:
                st.session_state[f"thin_pending_region_{image.id}"] = geometry
                st.rerun()
        pending = st.session_state.get(f"thin_pending_region_{image.id}")
        if pending:
            name = st.text_input("Название области", value=f"Область {len(fields) + 1}", key=f"thin_region_name_{image.id}")
            note = st.text_input("Комментарий", key=f"thin_region_note_{image.id}")
            c1, c2 = st.columns(2)
            if c1.button("Сохранить область", type="primary", key=f"thin_region_save_{image.id}", width="stretch"):
                create_slide_field(project_id, slide_image_id=image.id, name=name, description=note, geometry=pending)
                st.session_state.pop(f"thin_pending_region_{image.id}", None)
                st.rerun()
            if c2.button("Отменить", key=f"thin_region_cancel_{image.id}", width="stretch"):
                st.session_state.pop(f"thin_pending_region_{image.id}", None)
                st.rerun()
        return

    if mode == "Контур зерна":
        event = streamlit_image_coordinates(
            overlay,
            use_column_width="always",
            key=f"thin_grain_canvas_{image.id}",
        )
        token = int((event or {}).get("unix_time") or 0)
        state_key = f"thin_grain_event_{image.id}"
        if token and token != int(st.session_state.get(state_key, 0)):
            point = _event_point(event)
            st.session_state[state_key] = token
            if point:
                vertices.append(point)
                st.session_state[polygon_key] = vertices
                st.rerun()
        st.caption(f"Вершин контура: {len(vertices)}. Кликайте по границе зерна; для сохранения нужно минимум три точки.")
        name = st.text_input("Название зерна", value=f"Gr-{len([f for f in fields if _field_kind(f) == 'grain']) + 1}", key=f"thin_grain_name_{image.id}")
        note = st.text_input("Комментарий к зерну", key=f"thin_grain_note_{image.id}")
        c1, c2, c3 = st.columns(3)
        if c1.button("Сохранить контур", type="primary", disabled=len(vertices) < 3, key=f"thin_grain_save_{image.id}", width="stretch"):
            create_slide_field(
                project_id,
                slide_image_id=image.id,
                name=name,
                description=note,
                geometry={"kind": "grain", "vertices": [[float(x), float(y)] for x, y in vertices]},
            )
            st.session_state[polygon_key] = []
            st.rerun()
        if c2.button("Убрать последнюю", disabled=not vertices, key=f"thin_grain_undo_{image.id}", width="stretch"):
            st.session_state[polygon_key] = vertices[:-1]
            st.rerun()
        if c3.button("Очистить", disabled=not vertices, key=f"thin_grain_clear_{image.id}", width="stretch"):
            st.session_state[polygon_key] = []
            st.rerun()
        return

    event = streamlit_image_coordinates(
        overlay,
        use_column_width="always",
        key=f"thin_point_canvas_{image.id}",
    )
    token = int((event or {}).get("unix_time") or 0)
    state_key = f"thin_point_event_{image.id}"
    if token and token != int(st.session_state.get(state_key, 0)):
        point = _event_point(event)
        st.session_state[state_key] = token
        if point:
            st.session_state[f"thin_pending_point_{image.id}"] = point
            st.rerun()
    pending = st.session_state.get(f"thin_pending_point_{image.id}")
    if not pending:
        st.caption("Кликните по месту анализа на изображении.")
        return

    series = st.checkbox("Серия точек", key=f"thin_series_{image.id}", help="После сохранения номер автоматически увеличится на один.")
    prefix = st.text_input("Префикс", value="P-", key=f"thin_series_prefix_{image.id}") if series else ""
    number_key = f"thin_series_number_{image.id}"
    st.session_state.setdefault(number_key, 1)
    default_label = f"{prefix}{int(st.session_state[number_key])}" if series else ""
    label = st.text_input("Подпись точки", value=default_label, key=f"thin_point_label_{image.id}_{token or 'pending'}")
    analysis_query = st.text_input("Найти анализ для привязки", value=label, key=f"thin_point_query_{image.id}_{token or 'pending'}")
    analysis_ids, analysis_labels = _analysis_choices(project_id, analysis_query)
    selected = st.multiselect(
        "Связанные анализы",
        analysis_ids,
        format_func=lambda value: analysis_labels.get(value, value),
        key=f"thin_point_links_{image.id}_{token or 'pending'}",
        help="Можно связать несколько измерений одной физической позиции, например EPMA и LA-ICP-MS.",
    )
    note = st.text_input("Комментарий", key=f"thin_point_note_{image.id}_{token or 'pending'}")
    c1, c2 = st.columns(2)
    if c1.button("Сохранить точку", type="primary", key=f"thin_point_save_{image.id}", width="stretch"):
        create_slide_marker(
            project_id,
            slide_image_id=image.id,
            x_norm=float(pending[0]),
            y_norm=float(pending[1]),
            label=label,
            note=note,
            analysis_ids=tuple(selected),
        )
        if series:
            st.session_state[number_key] = int(st.session_state[number_key]) + 1
        st.session_state.pop(f"thin_pending_point_{image.id}", None)
        st.rerun()
    if c2.button("Отменить", key=f"thin_point_cancel_{image.id}", width="stretch"):
        st.session_state.pop(f"thin_pending_point_{image.id}", None)
        st.rerun()


def _links_tab(project_id: int, image, markers: list[dict], fields: list[dict]) -> None:
    linked_ids = sorted({str(value) for marker in markers for value in marker.get("analysis_ids", [])})
    selection = read_selection()
    selected_marker_ids = set(marker_ids_for_selection(markers, selection.analysis_ids))
    render_badges([
        (f"точек · {len(markers)}", "accent"),
        (f"связанных анализов · {len(linked_ids)}", "success" if linked_ids else "neutral"),
        (f"Selection на снимке · {len(selected_marker_ids)}", "success" if selected_marker_ids else "neutral"),
        (f"областей/контуров · {len(fields)}", "neutral"),
    ])
    if markers:
        frame = pd.DataFrame(markers)
        columns = [column for column in ("label", "entity_name", "field_name", "analysis_ids", "note", "x_norm", "y_norm") if column in frame.columns]
        st.dataframe(frame[columns], width="stretch", hide_index=True, height=320)

        marker_ids = [int(marker["id"]) for marker in markers]
        marker_by_id = {int(marker["id"]): marker for marker in markers}
        marker_id = st.selectbox(
            "Физическая точка",
            marker_ids,
            format_func=lambda value: str(marker_by_id[int(value)].get("label") or marker_by_id[int(value)].get("entity_name") or f"Точка {value}"),
            key=f"thin_link_marker_{image.id}",
        )
        marker_analysis_ids = analysis_ids_for_marker(markers, int(marker_id))
        m1, m2 = st.columns(2)
        if m1.button(
            f"Выбрать измерения · {len(marker_analysis_ids)}",
            disabled=not marker_analysis_ids,
            key=f"thin_select_marker_{image.id}",
            width="stretch",
        ):
            if _select_marker(project_id, markers, int(marker_id), image_title=str(image.title)):
                st.rerun()
        if m2.button(
            "Открыть в графиках",
            type="primary",
            disabled=not marker_analysis_ids,
            key=f"thin_plot_marker_{image.id}",
            width="stretch",
        ):
            _open_marker_in_plots(project_id, markers, int(marker_id), image_title=str(image.title))

    if linked_ids and st.button("Открыть все анализы этого снимка", width="stretch", key=f"thin_open_linked_analyses_{image.id}"):
        st.session_state["workflow_edit_analysis_ids"] = linked_ids
        st.session_state["workflow_edit_context"] = {"scope": "Шлиф", "analysis_ids": linked_ids}
        _go("analyses")

    with st.expander("Удалить разметку"):
        for marker in markers:
            label = str(marker.get("label") or marker.get("entity_name") or f"Точка {marker['id']}")
            if st.button(f"Удалить точку · {label}", key=f"thin_delete_marker_{marker['id']}"):
                delete_slide_marker(int(marker["id"]))
                st.rerun()
        for field in fields:
            if st.button(f"Удалить {_field_kind(field)} · {field.get('name')}", key=f"thin_delete_field_{field['id']}"):
                _delete_field(int(field["id"]))
                st.rerun()


def render_thin_section_workspace_page() -> None:
    project = active_project()
    render_page_header(
        "Работать со шлифом",
        "Выберите шлиф, откройте PPL/XPL/BSE и работайте с тем же Selection, что в таблицах и графиках.",
        eyebrow="Сценарий",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        return
    project_id = int(project["id"])
    sections = [item for item in list_entities(project_id) if item["kind"] == "thin_section"]
    _create_section(project_id)
    sections = [item for item in list_entities(project_id) if item["kind"] == "thin_section"]
    if not sections:
        st.info("Создайте первый шлиф. Его можно привязать к Sample сразу или позже.")
        return

    by_id = {int(item["id"]): item for item in sections}
    ids = list(by_id)
    pending_focus = st.session_state.pop("thin_section_focus_id_pending", None)
    if pending_focus is not None and int(pending_focus) in by_id:
        st.session_state["thin_section_selected"] = int(pending_focus)
    elif st.session_state.get("thin_section_selected") not in ids:
        st.session_state["thin_section_selected"] = ids[0]
    section_id = st.selectbox(
        "Шлиф",
        ids,
        format_func=lambda value: _section_label(by_id[int(value)]),
        key="thin_section_selected",
    )
    section = by_id[int(section_id)]
    images = [image for image in list_slide_images(project_id) if image.thin_section_id == int(section_id)]
    all_markers = [marker for image in images for marker in list_slide_markers(project_id, slide_image_id=image.id)]
    linked_ids = sorted({str(value) for marker in all_markers for value in marker.get("analysis_ids", [])})
    set_work_context(
        project_id=project_id,
        kind="thin_section",
        label=str(section["name"]),
        analysis_ids=linked_ids,
        sample=str(section.get("sample_name") or "") or None,
        sample_id=section.get("sample_id"),
        thin_section_id=int(section_id),
    )
    selection = read_selection()
    section_selection_markers = marker_ids_for_selection(all_markers, selection.analysis_ids)
    render_badges([
        (f"снимков · {len(images)}", "accent"),
        (f"точек · {len(all_markers)}", "neutral"),
        (f"связанных анализов · {len(linked_ids)}", "success" if linked_ids else "neutral"),
        (f"Selection здесь · {len(section_selection_markers)}", "success" if section_selection_markers else "neutral"),
    ])
    _quick_upload(project_id, int(section_id))
    images = [image for image in list_slide_images(project_id) if image.thin_section_id == int(section_id)]
    if not images:
        st.info("Добавьте PPL, XPL, BSE или другой снимок этого шлифа.")
        return

    image_by_id = {int(image.id): image for image in images}
    image_ids = list(image_by_id)
    pending_image = st.session_state.pop("thin_image_focus_id_pending", None)
    if pending_image is not None and int(pending_image) in image_by_id:
        st.session_state["thin_image_selected"] = int(pending_image)
    elif st.session_state.get("thin_image_selected") not in image_ids:
        st.session_state["thin_image_selected"] = image_ids[0]
    image_id = st.selectbox(
        "Снимок",
        image_ids,
        format_func=lambda value: f"{image_by_id[int(value)].title} · {image_by_id[int(value)].image_type}",
        key="thin_image_selected",
    )
    image = image_by_id[int(image_id)]
    markers = list_slide_markers(project_id, slide_image_id=image.id)
    fields = list_slide_fields(project_id, slide_image_id=image.id)

    pending_marker = st.session_state.pop("thin_marker_focus_id_pending", None)
    if pending_marker is not None and any(int(marker["id"]) == int(pending_marker) for marker in markers):
        st.session_state[f"thin_mode_{image.id}"] = "Просмотр"
        st.session_state[f"thin_local_search_{section_id}"] = ""

    annotate_tab, links_tab, images_tab = st.tabs(["Разметка", "Связи", "Снимки и управление"])
    with annotate_tab:
        _annotation_panel(project_id, image, markers, fields)
    with links_tab:
        _links_tab(project_id, image, markers, fields)
    with images_tab:
        st.caption("PPL, XPL и BSE одного шлифа хранятся как связанные снимки одного физического объекта. Разметка пока задаётся отдельно на каждом снимке, чтобы PetroLab не предполагал автоматическое совмещение без проверки.")
        view = pd.DataFrame([
            {
                "Название": item.title,
                "Тип": item.image_type,
                "Размер": f"{item.pixel_width} × {item.pixel_height}",
                "Оригинал": "доступен" if item.original_available else "только превью",
            }
            for item in images
        ])
        st.dataframe(view, width="stretch", hide_index=True)
        if st.button("Расширенное управление шлифами", width="stretch", key="thin_advanced"):
            _go("slides")
