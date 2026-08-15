from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.composite_points import (
    composite_point_provenance,
    composite_points_dataframe,
    list_physical_points,
    set_physical_point_links,
    sync_slide_markers_to_physical_points,
)
from petrolab.db import connect, list_accessible_datasets, load_dataset_dataframe
from petrolab.measurement_registry import create_entity, list_entities
from petrolab.slide_region_links import list_field_image_links, set_field_image_links
from petrolab.slides import list_slide_fields, list_slide_images, list_slide_markers
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


def _analysis_choices(project_id: int, query: str) -> tuple[list[str], dict[str, str]]:
    labels: dict[str, str] = {}
    needle = str(query or "").strip().casefold()
    for dataset in list_accessible_datasets(project_id):
        frame = load_dataset_dataframe(int(dataset["id"]), include_meta=True)
        if frame.empty or "_analysis_id" not in frame.columns:
            continue
        view = frame
        if needle:
            mask = view.astype(str).apply(
                lambda column: column.str.casefold().str.contains(needle, na=False, regex=False)
            ).any(axis=1)
            view = view.loc[mask]
        for _, row in view.head(350).iterrows():
            analysis_id = str(row["_analysis_id"])
            parts = [str(dataset.get("name") or f"Набор {dataset['id']}")]
            for column in ("Sample", "Grain", "Point", "Generation"):
                value = row.get(column)
                if value is not None and str(value).strip() and str(value).lower() != "nan":
                    parts.append(f"{column}: {value}")
            labels[analysis_id] = " · ".join(parts)[:220]
    ids = list(labels)[:1500]
    return ids, labels


def _existing_links(entity_id: int) -> list[str]:
    with connect() as con:
        rows = con.execute(
            "SELECT analysis_id FROM physical_point_analysis_links WHERE entity_id=? ORDER BY analysis_id",
            (int(entity_id),),
        ).fetchall()
    return [str(row["analysis_id"]) for row in rows]


def _point_images(project_id: int, entity_id: int) -> list[tuple[object, dict]]:
    images = {int(image.id): image for image in list_slide_images(project_id)}
    found: list[tuple[object, dict]] = []
    for marker in list_slide_markers(project_id):
        if marker.get("entity_id") is None or int(marker["entity_id"]) != int(entity_id):
            continue
        image = images.get(int(marker["slide_image_id"]))
        if image is not None:
            found.append((image, marker))
    return found


def _create_point(project_id: int, section: dict) -> None:
    with st.expander("＋ Физическая точка без готового маркера"):
        name = st.text_input("Название", placeholder="P-13", key="composite_new_point")
        note = st.text_input("Комментарий", key="composite_new_note")
        if st.button("Создать точку", type="primary", disabled=not name.strip(), key="composite_create"):
            try:
                create_entity(
                    project_id,
                    kind="probe_point",
                    name=name,
                    sample_id=section.get("sample_id"),
                    parent_id=int(section["id"]),
                    description=note,
                )
            except Exception as exc:
                st.error(str(exc))
            else:
                st.rerun()


def _render_region_image_links(project_id: int, section_id: int) -> None:
    """Let one mapped overview region own BSE/EDS/LA detail images without fake registration."""
    section_images = [
        image for image in list_slide_images(project_id)
        if image.thin_section_id == int(section_id)
    ]
    image_by_id = {int(image.id): image for image in section_images}
    image_ids = set(image_by_id)
    fields = [
        field for field in list_slide_fields(project_id)
        if int(field.get("slide_image_id") or -1) in image_ids
    ]
    if not fields:
        st.caption("Чтобы привязать EDS/BSE-снимок к участку, сначала нарисуйте область или контур на обзорном изображении шлифа.")
        return

    with st.expander("Снимки внутри размеченных областей", expanded=False):
        st.caption(
            "Здесь PetroLab фиксирует, что конкретный BSE/EDS/LA-снимок относится к выбранной области. "
            "Это явная пространственная связь, но не автоматическое пиксель-в-пиксель совмещение."
        )
        field_by_id = {int(field["id"]): field for field in fields}
        field_id = st.selectbox(
            "Область / зерно",
            list(field_by_id),
            format_func=lambda value: str(field_by_id[int(value)].get("name") or f"Поле {value}"),
            key=f"region_image_field_{section_id}",
        )
        field = field_by_id[int(field_id)]
        current_links = list_field_image_links(project_id, field_id=int(field_id))
        current_ids = [int(item["image_id"]) for item in current_links]
        overview_id = int(field.get("slide_image_id") or -1)
        candidates = [image_id for image_id in image_by_id if image_id != overview_id]
        options = list(dict.fromkeys([*current_ids, *candidates]))
        chosen = st.multiselect(
            "Какие детальные снимки относятся к этой области",
            options,
            default=[value for value in current_ids if value in options],
            format_func=lambda value: (
                f"{image_by_id[int(value)].title} · {image_by_id[int(value)].image_type}"
                if int(value) in image_by_id else str(value)
            ),
            key=f"region_image_links_{field_id}",
        )
        note = st.text_input(
            "Комментарий к связи",
            placeholder="EDS map этого зерна; BSE после анализа…",
            key=f"region_image_note_{field_id}",
        )
        if st.button("Сохранить снимки области", type="primary", width="stretch", key=f"region_image_save_{field_id}"):
            try:
                set_field_image_links(project_id, int(field_id), chosen, note=note)
            except Exception as exc:
                st.error(str(exc))
            else:
                st.success("Снимки привязаны к области.")
                st.rerun()

        linked = list_field_image_links(project_id, field_id=int(field_id))
        if linked:
            cols = st.columns(min(3, len(linked)))
            for index, item in enumerate(linked):
                image = image_by_id.get(int(item["image_id"]))
                if image is None:
                    continue
                with cols[index % len(cols)]:
                    preview = Path(image.preview_path)
                    if preview.is_file():
                        st.image(str(preview), caption=f"{image.title} · {image.image_type}", width="stretch")
                    if str(item.get("note") or "").strip():
                        st.caption(str(item["note"]))


def render_composite_points_page() -> None:
    project = active_project()
    render_page_header(
        "Совместить EDS / EPMA / LA",
        "Одна физическая точка может содержать несколько методов. Исходные аналитические строки остаются раздельными; для сравнения PetroLab строит безопасную composite-строку с provenance каждого значения.",
        eyebrow="Шлиф и анализы",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала выберите проект.")
        return
    project_id = int(project["id"])

    promoted = sync_slide_markers_to_physical_points(project_id)
    if promoted:
        st.caption(f"Из разметки шлифов синхронизировано новых физических точек: {promoted}.")

    sections = [item for item in list_entities(project_id) if item["kind"] == "thin_section"]
    if not sections:
        st.info("Сначала создайте шлиф и поставьте на нём аналитические точки.")
        if st.button("Работать со шлифом", type="primary", width="stretch"):
            navigate("thin_section")
            st.rerun()
        return
    by_section = {int(item["id"]): item for item in sections}
    section_id = st.selectbox(
        "Шлиф",
        list(by_section),
        format_func=lambda value: f"{by_section[int(value)]['name']} · {by_section[int(value)].get('sample_name') or 'без Sample'}",
        key="composite_section",
    )
    section = by_section[int(section_id)]
    _render_region_image_links(project_id, int(section_id))
    _create_point(project_id, section)

    points = list_physical_points(project_id, thin_section_id=int(section_id))
    if not points:
        st.info("На этом шлифе пока нет именованных физических точек. Поставьте маркер с подписью P-1/P-2… или создайте точку выше.")
        return
    by_point = {int(item["id"]): item for item in points}
    point_id = st.selectbox(
        "Физическая точка",
        list(by_point),
        format_func=lambda value: f"{by_point[int(value)]['name']} · связанных анализов {by_point[int(value)]['linked_analyses']}",
        key="composite_point",
    )
    point = by_point[int(point_id)]

    render_section_header("Связать методы", "Например: EDS/EPMA point 13 + LA-ICP-MS point 13")
    existing = _existing_links(int(point_id))
    query_default = str(point["name"])
    query = st.text_input(
        "Найти анализы",
        value=query_default,
        placeholder="номер точки, Sample, зерно, dataset…",
        key=f"composite_query_{point_id}",
    )
    analysis_ids, labels = _analysis_choices(project_id, query)
    options = list(dict.fromkeys([*existing, *analysis_ids]))
    selected = st.multiselect(
        "Эти анализы относятся к одной физической позиции",
        options,
        default=[value for value in existing if value in options],
        format_func=lambda value: labels.get(value, value),
        key=f"composite_links_{point_id}",
    )
    note = st.text_input(
        "Основание связи · необязательно",
        value="совпадает номер точки / положение на шлифе",
        key=f"composite_note_{point_id}",
    )
    if st.button("Сохранить физическую связь", type="primary", width="stretch", key=f"composite_save_{point_id}"):
        try:
            set_physical_point_links(project_id, int(point_id), selected, note=note)
        except Exception as exc:
            st.error(str(exc))
        else:
            st.success("Связь сохранена. Исходные EDS/EPMA/LA анализы не изменены.")
            st.rerun()

    images = _point_images(project_id, int(point_id))
    if images:
        with st.expander("Где эта точка видна на снимках", expanded=False):
            cols = st.columns(min(3, len(images)))
            for index, (image, marker) in enumerate(images):
                with cols[index % len(cols)]:
                    preview = Path(image.preview_path)
                    if preview.is_file():
                        st.image(str(preview), caption=f"{image.title} · {image.image_type}", width="stretch")
                    st.caption(f"Маркер: {marker.get('label') or point['name']}")

    render_section_header("Composite analysis", "Значения разных методов доступны как одна строка для графика")
    composite = composite_points_dataframe(project_id, thin_section_id=int(section_id))
    if composite.empty:
        st.caption("Свяжите хотя бы один импортированный анализ с физической точкой.")
        return
    current = composite[composite["_physical_point_id"].astype(int).eq(int(point_id))]
    if not current.empty:
        row = current.iloc[0]
        conflict_text = str(row.get("Конфликты методов") or "").strip()
        render_badges([
            (f"связано · {int(row.get('Связанных анализов', 0))}", "accent"),
            ("конфликтов нет" if not conflict_text else f"конфликты · {len([x for x in conflict_text.split(',') if x.strip()])}", "success" if not conflict_text else "warning"),
        ])
        if conflict_text:
            st.warning(
                "Один и тот же параметр имеет разные значения в нескольких методах: " + conflict_text + ". PetroLab не выбирает одно из них автоматически; используйте колонки с названием метода/dataset."
            )
        visible = [column for column in current.columns if not str(column).startswith("_")]
        st.dataframe(current[visible], width="stretch", hide_index=True)
        with st.expander("Provenance по каждому значению", expanded=False):
            provenance = composite_point_provenance(row)
            provenance_rows = []
            for analyte, items in provenance.items():
                for item in items:
                    provenance_rows.append({"Поле": analyte, **item})
            if provenance_rows:
                st.dataframe(pd.DataFrame(provenance_rows), width="stretch", hide_index=True, height=380)

    c1, c2 = st.columns(2)
    if c1.button("Все composite-точки этого шлифа", width="stretch", key="composite_show_all"):
        st.session_state["composite_show_all_table"] = not bool(st.session_state.get("composite_show_all_table", False))
        st.rerun()
    if c2.button("Сравнить composite-точки на нескольких графиках", type="primary", width="stretch", key="composite_to_panels"):
        st.session_state["multi_panel_data_mode"] = "Физические точки EDS + LA"
        st.session_state["multi_panel_thin_section_id"] = int(section_id)
        navigate("multi_panel")
        st.rerun()
    if st.session_state.get("composite_show_all_table"):
        visible = [column for column in composite.columns if not str(column).startswith("_")]
        st.dataframe(composite[visible], width="stretch", hide_index=True, height=520)
