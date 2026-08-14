from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_accessible_datasets, load_dataset_dataframe
from petrolab.measurement_registry import create_entity, list_entities
from petrolab.sample_registry import list_samples
from petrolab.slides import (
    IMAGE_TYPES,
    STORAGE_LINKED,
    create_slide_field,
    create_slide_marker,
    delete_slide_image,
    delete_slide_marker,
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
    st.caption("Координаты — в процентах от левого верхнего угла. Их можно уточнить по лёгкому превью справа.")
    x_col, y_col = st.columns(2)
    with x_col:
        x_percent = st.number_input("X, %", min_value=0.0, max_value=100.0, value=50.0, step=0.1, key=f"{prefix}_x")
    with y_col:
        y_percent = st.number_input("Y, %", min_value=0.0, max_value=100.0, value=50.0, step=0.1, key=f"{prefix}_y")
    return float(x_percent) / 100, float(y_percent) / 100


def _add_field(project_id: int, images: list) -> None:
    render_section_header("2. Поле", "Необязательная группа для участка шлифа")
    image = _image_choice(images, "slide_field_image")
    st.caption("Поле — это понятная подпись участка (например, «край зерна 3»). Границы можно не задавать.")
    name = st.text_input("Название поля", placeholder="Поле 1 — флогопит", key="slide_field_name")
    note = st.text_input("Заметка (необязательно)", key="slide_field_note")
    with st.expander("Отметить прямоугольник на превью (необязательно)"):
        x_norm, y_norm = _coordinate_inputs("slide_field")
        size_col, _ = st.columns(2)
        with size_col:
            width_percent = st.number_input("Ширина, %", min_value=0.1, max_value=100.0, value=20.0, step=0.1, key="slide_field_w")
        height_percent = st.number_input("Высота, %", min_value=0.1, max_value=100.0, value=20.0, step=0.1, key="slide_field_h")
        geometry = {"x": x_norm, "y": y_norm, "width": float(width_percent) / 100, "height": float(height_percent) / 100}
    if st.button("Добавить поле", type="primary", key="slide_add_field"):
        try:
            create_slide_field(project_id, slide_image_id=image.id, name=name, description=note, geometry=geometry if "geometry" in locals() else None)
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
    selected_analysis = st.multiselect(
        "Связанные строки анализа (можно несколько)", analysis_ids,
        format_func=lambda value: analysis_labels.get(value, value), key="slide_marker_analysis_ids",
        help="Так EDS, EPMA и LA остаются отдельными измерениями, но показываются в одном месте шлифа.",
    )
    label = st.text_input("Подпись метки", placeholder="Mica-3 / EDS-17", key="slide_marker_label")
    note = st.text_input("Заметка (необязательно)", key="slide_marker_note")
    left, right = st.columns([1, 1.3])
    with left:
        x_norm, y_norm = _coordinate_inputs("slide_marker")
    with right:
        try:
            st.image(image.preview_path, caption="Лёгкое превью — ориентир для координат", width="stretch")
        except Exception:
            st.warning("Превью недоступно. Перепривяжите исходный снимок на вкладке «Карта»." )
    if st.button("Поставить метку", type="primary", key="slide_add_marker"):
        if entity_id is None and not selected_analysis:
            st.warning("Выберите физическую сущность или хотя бы одну строку анализа — иначе метка ничего не объясняет.")
            return
        try:
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
    add_tab, field_tab, marker_tab, map_tab = st.tabs(["1 · Снимок", "2 · Поле", "3 · Метки", "Карта"])
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
