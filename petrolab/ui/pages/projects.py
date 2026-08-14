from __future__ import annotations

import tempfile
from pathlib import Path

import streamlit as st

from petrolab.db import create_project, list_accessible_datasets, list_datasets, list_projects
from petrolab.fragment_archive import create_fragment_archive
from petrolab.measurement_registry import list_entities
from petrolab.project_archive import create_project_archive, restore_project_archive
from petrolab.sample_registry import list_samples
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
        mode_label = st.radio("Состав архива", list(mode_labels), key=f"archive_mode_{project_id}")
        mode = mode_labels[mode_label]
        image_mode = "none"
        if mode == "full":
            image_labels = {
                "Оригиналы — научный архив": "originals",
                "Оптимизированные копии — меньше размер": "optimized",
            }
            image_label = st.radio("Изображения", list(image_labels), key=f"archive_images_{project_id}")
            image_mode = image_labels[image_label]
            if image_mode == "optimized":
                st.caption("Сжатые изображения помечаются как производные копии и не заменяют исходные TIFF/BSE.")
        if st.button("Подготовить переносимый архив", key=f"build_archive_{project_id}"):
            try:
                with tempfile.TemporaryDirectory(prefix="petrolab_export_") as tmp:
                    filename = f"{project['name']}.petrolab"
                    result = create_project_archive(
                        project_id,
                        Path(tmp) / filename,
                        mode=mode,
                        image_mode=image_mode,
                    )
                    payload = result.path.read_bytes()
                st.session_state[f"project_archive_bytes_{project_id}"] = payload
                st.session_state[f"project_archive_name_{project_id}"] = filename
                st.session_state[f"project_archive_meta_{project_id}"] = (
                    result.dataset_count, result.source_count, result.image_count,
                )
            except Exception as exc:
                st.error(f"Не удалось создать архив: {exc}")
        payload = st.session_state.get(f"project_archive_bytes_{project_id}")
        if payload:
            dataset_count, source_count, image_count = st.session_state.get(
                f"project_archive_meta_{project_id}", (0, 0, 0)
            )
            st.caption(
                f"Готово: {dataset_count} наборов, {source_count} исходных файлов, {image_count} изображений."
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


def _fragment_controls(project: dict) -> None:
    project_id = int(project["id"])
    with st.expander("Передать часть данных", expanded=False):
        st.caption(
            "Соберите маленький .petrolab: например, один шлиф только с EDS-точками, "
            "только с LA-ICP-MS кратерами или с обоими типами данных. Остальной проект в пакет не попадёт."
        )
        samples = list_samples(project_id)
        if not samples:
            st.info("Сначала добавьте Sample в реестр проекта.")
            return
        sample_by_id = {int(row["id"]): row for row in samples}
        sample_id = int(st.selectbox(
            "Sample",
            list(sample_by_id),
            format_func=lambda value: str(sample_by_id[int(value)]["name"]),
            key=f"fragment_sample_{project_id}",
        ))

        entities = list_entities(project_id, sample_id=sample_id)
        sections = [row for row in entities if str(row.get("kind")) == "thin_section"]
        section_by_id = {int(row["id"]): row for row in sections}
        selected_sections = st.multiselect(
            "Шлифы",
            list(section_by_id),
            default=list(section_by_id),
            format_func=lambda value: str(section_by_id[int(value)]["name"]),
            key=f"fragment_sections_{project_id}_{sample_id}",
            help="Можно выбрать один шлиф или несколько. Если физические объекты ещё не заведены, используйте datasets ниже.",
        ) if sections else []
        if not sections:
            st.caption("Для этого Sample пока нет зарегистрированных шлифов. Можно передать выбранные datasets целиком.")

        col1, col2, col3 = st.columns(3)
        with col1:
            include_eds = st.checkbox(
                "EDS / микрозонд",
                value=True,
                key=f"fragment_eds_{project_id}_{sample_id}",
                help="Точечные probe_point и наблюдения EDS/EPMA/WDS.",
            )
        with col2:
            include_la = st.checkbox(
                "LA-ICP-MS",
                value=True,
                key=f"fragment_la_{project_id}_{sample_id}",
            )
        with col3:
            include_other = st.checkbox(
                "Другие наблюдения",
                value=False,
                key=f"fragment_other_{project_id}_{sample_id}",
            )

        accessible = list_accessible_datasets(project_id)
        sample_datasets = []
        for row in accessible:
            value = row.get("sample_id")
            if value is not None and int(value) == sample_id:
                sample_datasets.append(row)
        dataset_by_id = {int(row["id"]): row for row in sample_datasets}
        selected_datasets = st.multiselect(
            "Дополнительно передать datasets целиком",
            list(dataset_by_id),
            default=[],
            format_func=lambda value: str(dataset_by_id[int(value)].get("name") or f"Dataset {value}"),
            key=f"fragment_datasets_{project_id}_{sample_id}",
            help="Нужно прежде всего для старых импортов, где точки ещё не связаны с физическим реестром.",
        ) if dataset_by_id else []

        include_images = st.checkbox(
            "Включить связанные изображения",
            value=True,
            key=f"fragment_images_{project_id}_{sample_id}",
        )
        include_sources = st.checkbox(
            "Включить исходные Excel/CSV",
            value=False,
            key=f"fragment_sources_{project_id}_{sample_id}",
            help="Обычно выключено: исходный Excel может содержать больше данных, чем выбранный фрагмент.",
        )

        if st.button("Подготовить фрагмент .petrolab", type="primary", key=f"build_fragment_{project_id}"):
            try:
                sample_name = str(sample_by_id[sample_id]["name"])
                with tempfile.TemporaryDirectory(prefix="petrolab_fragment_ui_") as tmp:
                    filename = f"{sample_name}_fragment.petrolab"
                    result = create_fragment_archive(
                        project_id,
                        sample_id,
                        Path(tmp) / filename,
                        thin_section_ids=selected_sections,
                        include_eds=include_eds,
                        include_la=include_la,
                        include_other=include_other,
                        extra_dataset_ids=selected_datasets,
                        include_images=include_images,
                        include_sources=include_sources,
                    )
                    payload = result.path.read_bytes()
                st.session_state[f"fragment_archive_bytes_{project_id}"] = payload
                st.session_state[f"fragment_archive_name_{project_id}"] = filename
                st.session_state[f"fragment_archive_meta_{project_id}"] = result
            except Exception as exc:
                st.error(f"Не удалось создать фрагмент: {exc}")

        payload = st.session_state.get(f"fragment_archive_bytes_{project_id}")
        result = st.session_state.get(f"fragment_archive_meta_{project_id}")
        if payload and result:
            st.caption(
                f"Готово: {result.thin_section_count} шлиф., {result.entity_count} физических объектов, "
                f"{result.observation_count} наблюдений, {result.analysis_count} аналитических точек, "
                f"{result.image_count} изображений."
            )
            st.download_button(
                "Скачать фрагмент .petrolab",
                data=payload,
                file_name=st.session_state.get(
                    f"fragment_archive_name_{project_id}", "PetroLab_fragment.petrolab"
                ),
                mime="application/zip",
                key=f"download_fragment_{project_id}",
            )


def _restore_controls(projects_exist: bool) -> None:
    with st.expander("Открыть переносимый .petrolab", expanded=not projects_exist):
        st.caption(
            "Полный проект можно восстановить как workspace. Маленькие фрагменты добавляются через "
            "раздел «Совместная работа» и никогда не заменяют всю базу."
        )
        uploaded = st.file_uploader("Архив PetroLab", type=["petrolab"], key="restore_petrolab_upload")
        replace = False
        if projects_exist:
            st.warning(
                "В текущем workspace уже есть проекты. Замена допустима только после явного подтверждения; "
                "перед ней создаётся backup SQLite. Для добавления данных используйте «Совместная работа»."
            )
            replace = st.checkbox(
                "Я понимаю: заменить текущий workspace восстановленным проектом",
                value=False,
                key="restore_replace_workspace",
            )
        if uploaded is not None and st.button(
            "Восстановить проект",
            type="primary",
            disabled=projects_exist and not replace,
            key="restore_petrolab_btn",
        ):
            try:
                with tempfile.TemporaryDirectory(prefix="petrolab_restore_upload_") as tmp:
                    path = Path(tmp) / Path(uploaded.name).name
                    path.write_bytes(uploaded.getvalue())
                    result = restore_project_archive(path, allow_replace_workspace=replace)
                st.session_state["active_project_id"] = int(result.project_id)
                st.session_state["sidebar_project"] = int(result.project_id)
                if result.backup_path:
                    st.success(
                        f"Проект «{result.project_name}» восстановлен. "
                        f"Предыдущая база сохранена: {result.backup_path.name}"
                    )
                else:
                    st.success(f"Проект «{result.project_name}» восстановлен.")
                st.rerun()
            except Exception as exc:
                st.error(f"Не удалось восстановить архив: {exc}")


def render_projects_page() -> None:
    render_page_header(
        "Проекты",
        "Проект — постоянный научный контекст для источников, анализов, изображений, пород и публикационных данных.",
        eyebrow="Система",
    )
    projects = list_projects()
    _restore_controls(bool(projects))
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
                    "Открыть",
                    key=f"open_project_{project_id}",
                    disabled=active,
                    type="primary" if not active else "secondary",
                    width="stretch",
                ):
                    st.session_state["active_project_id"] = project_id
                    st.session_state["sidebar_project"] = project_id
                    navigate("home")
                    st.rerun()
            _fragment_controls(project)
            _portable_archive_controls(project)
