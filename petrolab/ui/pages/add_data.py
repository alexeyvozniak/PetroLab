from __future__ import annotations

import streamlit as st

from petrolab.ui.intake_workflow import render_intake_workflow
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


def render_add_data_page() -> None:
    project = active_project()
    render_page_header(
        "Добавить данные",
        "Перетащите файл один раз. PetroLab сначала определит, что это, покажет предпросмотр и только затем предложит Sample, mineral, provenance и привязку изображений.",
        eyebrow="Данные",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        if st.button("Открыть проекты", type="primary", key="add_data_projects"):
            navigate("projects")
            st.rerun()
        return

    render_badges([
        ("Excel / CSV", "accent"),
        ("PPL / XPL / BSE / карты", "neutral"),
        ("BMP / PNG / JPG / TIFF", "neutral"),
        ("allow but warn", "success"),
    ])
    st.caption(
        "Один обычный путь: файл → листы/колонки → разнести строки по Sample → проверить → сохранить → "
        "при необходимости добавить изображения и связать их с теми же точками. "
        "Статья или данные коллеги отличаются только provenance, а не отдельной системой импорта."
    )
    render_intake_workflow(int(project["id"]))
