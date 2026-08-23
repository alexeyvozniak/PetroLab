from __future__ import annotations

import json

import streamlit as st

from petrolab.db import list_plot_recipes
from petrolab.figure_composer import compose_figure, image_bytes
from petrolab.figure_recipes import LAYOUTS, PANEL_TYPES, delete_figure_recipe, list_figure_recipes, save_figure_recipe
from petrolab.publication_manifest import manifest_json_bytes
from petrolab.ui.layout import render_page_header, render_section_header
from petrolab.ui.project_context import active_project


def _render_composer(record: dict) -> None:
    """Turn the reproducible recipe into a reviewable mixed publication image."""
    with st.expander("Собрать PNG/PDF из готовых панелей", expanded=False):
        st.caption(
            "Загрузите экспортированные PNG/JPG/WebP панели. PetroLab сохранит их пропорции, поставит подписи "
            "A–F и отдаст один PNG, PDF и тот же manifest. Исходные SVG остаются самостоятельными векторными файлами."
        )
        panels: dict[str, bytes] = {}
        filenames: dict[str, str] = {}
        for cell in record["cells"]:
            position = str(cell["position"])
            upload = st.file_uploader(
                f"Панель {position} · {cell['type']} · {cell['reference'] or 'внешний файл'}",
                type=["png", "jpg", "jpeg", "webp"], key=f"figure_compose_{record['id']}_{position}",
            )
            if upload is not None:
                panels[position] = upload.getvalue()
                filenames[position] = upload.name
        if len(panels) != len(record["cells"]):
            st.caption(f"Загружено панелей: {len(panels)} из {len(record['cells'])}.")
            return
        try:
            composed = compose_figure(layout_name=str(record["layout_name"]), cells=record["cells"], panels=panels)
            png = image_bytes(composed, "png")
            pdf = image_bytes(composed, "pdf")
        except Exception as exc:
            st.error(f"Не удалось собрать Figure Recipe: {exc}")
            return
        st.image(png, caption=f"{record['name']} · preview", width="stretch")
        composed_manifest = {
            "schema": "petrolab-figure-composite/v1", "recipe_id": record["id"], "name": record["name"],
            "layout": record["layout_name"], "cells": record["cells"], "panel_files": filenames,
            "note": record["note"], "updated_at": record["updated_at"],
        }
        base_name = str(record["name"]).replace("/", "_").replace("\\", "_")
        left, middle, right = st.columns(3)
        left.download_button("PNG composite", png, file_name=f"{base_name}.png", mime="image/png", key=f"figure_png_{record['id']}")
        middle.download_button("PDF composite", pdf, file_name=f"{base_name}.pdf", mime="application/pdf", key=f"figure_pdf_{record['id']}")
        right.download_button("Composite manifest", manifest_json_bytes(composed_manifest), file_name=f"{base_name}_composite_manifest.json", mime="application/json", key=f"figure_composite_manifest_{record['id']}")


def _chart_type(config: dict) -> str:
    value = str(config.get("chart_type") or "").casefold()
    if "ternary" in value or "треуг" in value:
        return "Треугольная"
    if "spider" in value or "ree" in value:
        return "REE / Spider"
    return "XY"


def render_figure_recipes_page() -> None:
    project = active_project()
    render_page_header("Figure Recipe", "Соберите mixed-компоновку для статьи из XY, треугольных и REE/spider-панелей без потери рецептов и источников.", eyebrow="Публикация")
    if project is None:
        st.info("Сначала выберите проект.")
        return
    project_id = int(project["id"])
    records = list_plot_recipes(project_id)
    by_type = {panel_type: [] for panel_type in PANEL_TYPES}
    for record in records:
        by_type.setdefault(_chart_type(record.get("config", {})), []).append(record)
    render_section_header("Новая компоновка", "Рецепт связывает панели по их настройкам; файл figure manifest фиксирует порядок, подписи и источники")
    layout_name = st.selectbox("Сетка", list(LAYOUTS), index=2, key="figure_recipe_layout")
    columns, rows = LAYOUTS[layout_name]
    capacity = columns * rows
    cells: list[dict] = []
    for index in range(capacity):
        with st.expander(f"Панель {chr(65 + index)}", expanded=index < 2):
            panel_type = st.selectbox("Тип", PANEL_TYPES, key=f"figure_recipe_type_{index}")
            candidates = by_type.get(panel_type, [])
            if panel_type == "Внешний SVG/PNG":
                reference = st.text_input("Файл / путь к готовой панели", key=f"figure_recipe_ref_{index}")
            elif candidates:
                options = {f"{record['name']} · {record.get('updated_at', '')}": record for record in candidates}
                selected = st.selectbox("Сохранённый рецепт панели", list(options), key=f"figure_recipe_ref_{index}")
                reference = str(options[selected]["name"])
            else:
                st.warning(f"Сначала сохраните хотя бы один рецепт типа «{panel_type}» в соответствующем графике.")
                reference = ""
            caption = st.text_input("Подпись панели", value=chr(65 + index), key=f"figure_recipe_caption_{index}")
            cells.append({"position": chr(65 + index), "type": panel_type, "reference": reference, "caption": caption})
    name = st.text_input("Название Figure Recipe", placeholder="Figure 4: mica evolution")
    note = st.text_area("Заметка", placeholder="Панели A–F; версия для Lithos")
    if st.button("Сохранить Figure Recipe", type="primary", disabled=not name, key="figure_recipe_save"):
        try:
            save_figure_recipe(project_id, name=name, layout_name=layout_name, cells=cells, note=note)
        except Exception as exc:
            st.error(f"Figure Recipe не сохранён: {exc}")
        else:
            st.success("Figure Recipe сохранён. Его JSON manifest можно положить рядом с SVG/PNG при подготовке статьи.")
            st.rerun()

    render_section_header("Сохранённые Figure Recipes", "Каждый хранит состав mixed-компоновки, а не скриншот")
    for record in list_figure_recipes(project_id):
        st.markdown(f"**{record['name']}** · {record['layout_name']}  \n{record['note'] or 'без заметки'}")
        st.dataframe(record["cells"], width="stretch", hide_index=True)
        manifest = {"schema": "petrolab-figure-recipe/v1", "id": record["id"], "name": record["name"], "layout": record["layout_name"], "cells": record["cells"], "note": record["note"], "updated_at": record["updated_at"]}
        left, right = st.columns(2)
        left.download_button("JSON manifest", manifest_json_bytes(manifest), file_name=f"{record['name']}_figure_recipe.json", mime="application/json", key=f"figure_manifest_{record['id']}")
        if right.button("Удалить", key=f"figure_recipe_delete_{record['id']}"):
            delete_figure_recipe(int(record["id"]))
            st.rerun()
        _render_composer(record)
