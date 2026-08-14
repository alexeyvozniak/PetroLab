from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from petrolab.db import create_project, list_datasets, list_projects
from petrolab.project_archive import create_project_archive
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate


def _portable_archive_controls(project: dict) -> None:
    project_id = int(project["id"])
    with st.expander("Перенос и резервная копия", expanded=False):
        st.caption(
            "Создайте один файл .petrolab для другого компьютера или резервной копии. "
            "Исходные Excel и изображения можно включать отдельно."
        )
        mode_labels = {
            "Только проект": "project",
            "Проект + Excel/CSV": "project_sources",
            "Полный проект + Excel/CSV + изображения": "full",
        }
        mode_label = st.radio(
            "Состав архива",
            list(mode_labels),
            key=f"archive_mode_{project_id}",
        )
        mode = mode_labels[mode_label]
        if mode == "full":
            st.info("В полном архиве изображения сохраняются в исходном качестве.")
        if st.button("Подготовить переносимый архив", key=f"build_archive_{project_id}"):
            try:
                with tempfile.TemporaryDirectory(prefix="petrolab_export_") as tmp:
                    filename = f"{project['name']}.petrolab"
                    result = create_project_archive(
                        project_id,
                        Path(tmp) / filename,
                        mode=mode,
                        image_mode="originals" if mode == "full" else "none",
                    )
                    payload = result.path.read_bytes()
                st.session_state[f"project_archive_bytes_{project_id}"] = payload
                st.session_state[f"project_archive_name_{project_id}"] = filename
                st.session_state[f"project_archive_meta_{project_id}"] = (
                    result.dataset_count,
                    result.source_count,
                    result.image_count,
                )
            except Exception as exc:
                st.error(f"Не удалось создать архив: {exc}")
        payload = st.session_state.get(f"project_archive_bytes_{project_id}")
        if payload:
            dataset_count, source_count, image_count = st.session_state.get(
                f"project_archive_meta_{project_id}", (0, 0, 0)
            )
            st.caption(
                f"Готово: {dataset_count} наборов, {source_count} исходных файлов, "
                f"{image_count} изображений."
            )
            st.download_button(
                "Скачать .petrolab",
                data=payload,
                file_name=st.session_state.get(
                    f"project_archive_name_{project_id}", "PetroLab_project.petrolab"
                ),
                mime="application/zip",
                key=f"download_archive_{project_id}",
            )


def render_projects_page() -> None:
    render_page_header(
        "Проекты",
        "Проект — постоянный научный контекст для источников, анализов, изображений, пород и публикационных данных.",
        eyebrow="Система",
    )
    projects = list_projects()
    with st.expander("+ Новый проект", expanded=not bool(projects)):
        with st.form("new_project", clear_on_submit=True):
            name = st.text_input("Название", placeholder="Например, Kola lamprophyres")
            description = st.text_area("Краткое описание", placeholder="Объекты, задача или статья")
            if st.form_submit_button("Создать проект", type="primary"):
                try:
                    project_id = create_project(name, description)
                    st.session_state["active_project_id"] = int(project_id)
                    st.success(f"Проект «{name.strip()}» создан.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))

    if not projects:
        return
    render_section_header("Все проекты", "Активный проект используется во всех рабочих разделах")
    active_id = str(st.session_state.get("active_project_id", ""))
    for project in projects:
        project_id = int(project["id"])
        datasets = list_datasets(project_id)
        rows = sum(int(item.get("row_count") or 0) for item in datasets)
        active = active_id == str(project_id)
        with st.container(border=True):
            info, action = st.columns([4, 1])
            with info:
                st.markdown(f"### {project['name']}")
                if project.get("description"):
                    st.caption(str(project["description"]))
                render_badges([
                    ("✓ Активный" if active else "○ Проект", "accent" if active else "neutral"),
                    (f"{len(datasets)} наборов", "neutral"),
                    (f"{rows:,} анализов".replace(",", " "), "neutral"),
                ])
            with action:
                st.write("")
                if st.button(
                    "Открыть", key=f"open_project_{project_id}", disabled=active,
                    type="primary" if not active else "secondary", width="stretch",
                ):
                    st.session_state["active_project_id"] = project_id
                    st.session_state["sidebar_project"] = project_id
                    navigate("home")
                    st.rerun()
            _portable_archive_controls(project)
