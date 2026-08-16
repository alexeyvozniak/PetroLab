from __future__ import annotations

import streamlit as st

from petrolab.analytical_sessions import TECHNIQUES, list_sessions, session_datasets
from petrolab.db import list_accessible_datasets
from petrolab.derived import formula_status
from petrolab.formula_workflow import recommended_method
from petrolab.services.image_service import list_dataset_images
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


def _jump(route: str) -> None:
    navigate(route)
    st.rerun()


def _dataset_label(dataset: dict) -> str:
    name = str(dataset.get("name") or f"Набор {dataset['id']}")
    mineral = str(dataset.get("mineral_key") or "generic")
    rows = int(dataset.get("row_count") or 0)
    return f"{name} · {mineral} · {rows} точек"


def _is_mixed(dataset: dict) -> bool:
    name = str(dataset.get("name") or "").casefold()
    return str(dataset.get("mineral_key") or "generic") == "generic" or "mixed" in name or "неразобран" in name


def _session_summary(project_id: int) -> None:
    sessions = list_sessions(project_id)
    render_section_header("1 · Образец и аналитическая сессия", "Один Sample — несколько независимых методов")
    if not sessions:
        st.info("Сначала удобно завести Sample и сессию: например EPMA/WDS отдельно, LA-ICP-MS отдельно. Их можно связать с тем же зерном и шлифом позже.")
    else:
        recent = sessions[0]
        technique = TECHNIQUES.get(str(recent.get("technique")), str(recent.get("technique") or ""))
        render_badges([
            (f"последний Sample · {recent.get('sample_name', '')}", "accent"),
            (technique, "neutral"),
            (f"сессий в проекте · {len(sessions)}", "neutral"),
        ])
        st.caption("EPMA/EDS и LA-ICP-MS не сливаются в одно измерение: они остаются отдельными сессиями того же Sample и могут быть связаны через зерно, точку/кратер и шлиф.")
    if st.button("Открыть Samples и сессии", key="workflow_sessions", width="stretch"):
        _jump("sessions")


def _dataset_selector(project_id: int) -> tuple[dict | None, list[dict]]:
    render_section_header("2 · Файл и рабочий набор", "Импорт один раз; проект получает ссылку без копирования химии")
    datasets = list_accessible_datasets(project_id)
    if not datasets:
        st.info("В проекте ещё нет анализов. Импортируйте Excel/CSV — PetroLab сначала покажет листы, колонки, Fe-семантику и QC.")
        if st.button("Импортировать зонд / EDS / LA / другой файл", type="primary", key="workflow_import_empty", width="stretch"):
            _jump("add_data")
        return None, []

    requested = st.session_state.get("workflow_focus_dataset_id")
    ids = [int(item["id"]) for item in datasets]
    default_id = int(requested) if requested is not None and int(requested) in ids else ids[0]
    by_id = {int(item["id"]): item for item in datasets}
    selected_id = st.selectbox(
        "С чем работаем сейчас",
        ids,
        index=ids.index(default_id),
        format_func=lambda value: _dataset_label(by_id[int(value)]),
        key="workflow_dataset",
    )
    dataset = by_id[int(selected_id)]
    st.session_state["workflow_focus_dataset_id"] = int(selected_id)
    render_badges([
        (f"{dataset.get('source_filename') or 'источник'}", "neutral"),
        (f"{int(dataset.get('row_count') or 0)} анализов", "accent"),
        ("в активном проекте", "success"),
        ("mixed / требует разбора" if _is_mixed(dataset) else f"модуль · {dataset.get('mineral_key')}", "warning" if _is_mixed(dataset) else "success"),
    ])
    c1, c2 = st.columns(2)
    if c1.button("Добавить ещё файл", key="workflow_import_more", width="stretch"):
        _jump("add_data")
    if c2.button("Открыть базу анализов", key="workflow_open_analyses", width="stretch"):
        st.session_state["workflow_edit_dataset_ids"] = [int(selected_id)]
        _jump("analyses")
    return dataset, datasets


def _dataset_session_context(project_id: int, dataset: dict) -> None:
    sessions = list_sessions(project_id)
    linked = []
    for session in sessions:
        try:
            ids = {int(item["id"]) for item in session_datasets(int(session["id"]))}
        except (KeyError, ValueError):
            continue
        if int(dataset["id"]) in ids:
            linked.append(session)

    if not linked:
        st.warning(
            "Этот набор ещё не привязан к canonical Sample / аналитической сессии. PetroLab не угадывает Sample автоматически: один Excel может содержать несколько образцов."
        )
        if st.button("Привязать набор к Sample и сессии", key="workflow_attach_session", width="stretch"):
            _jump("sessions")
        return

    badges = []
    for session in linked[:3]:
        technique = TECHNIQUES.get(str(session.get("technique")), str(session.get("technique") or ""))
        badges.extend([
            (f"Sample · {session.get('sample_name', '')}", "accent"),
            (technique, "success"),
        ])
    render_badges(badges)
    if len(linked) > 3:
        st.caption(f"И ещё сессий: {len(linked) - 3}.")


def _phase_step(dataset: dict) -> None:
    render_section_header("3 · Фазы, mixed и выбросы", "Сначала понять, что за точки; ничего не удалять автоматически")
    if _is_mixed(dataset):
        st.warning(
            "Этот набор считается смешанным или неразобранным. PetroLab предложит минералы, отметит потенциальные химические выбросы и оставит спорные точки в «Неразобранные / mixed»."
        )
        label = "Разобрать оставшиеся mixed и выбросы" if "mixed" in str(dataset.get("name") or "").casefold() else "Разобрать фазы и выбросы"
        if st.button(label, type="primary", key="workflow_phase_review", width="stretch"):
            st.session_state["workflow_mixed_dataset_id"] = int(dataset["id"])
            _jump("mixed_minerals")
    else:
        st.success("Набор уже относится к минералогическому модулю. При желании его всё равно можно проверить на ошибочные фазы и химические выбросы.")
        if st.button("Проверить фазы и выбросы", key="workflow_phase_sanity", width="stretch"):
            st.session_state["workflow_mixed_dataset_id"] = int(dataset["id"])
            _jump("mixed_minerals")
    st.caption("Потенциальный выброс — только предупреждение. Он не исключается из графиков и не переносится автоматически; необычный природный состав может быть важным.")


def _formula_step(dataset: dict) -> None:
    render_section_header("4 · Формулы и APFU", "Только валидированный метод для выбранного минералогического модуля")
    method = recommended_method(str(dataset.get("mineral_key") or "generic"))
    if method is None:
        st.caption("Для этого набора нет безопасного автоматического структурного пересчёта. Химия, изображения и графики доступны без формулы.")
        return
    status = formula_status(int(dataset["id"]))
    if status.has_active_formula:
        render_badges([
            (f"формула · {status.method_title or status.method_id}", "success"),
            (f"актуально {status.current_rows}/{status.total_rows}", "success" if status.stale_rows == 0 else "warning"),
        ])
        button_label = "Пересмотреть формулу"
    else:
        st.info(f"Рекомендуемый стартовый метод: {method.title_ru}. Он будет показан до сохранения и не применяется молча.")
        button_label = "Рассчитать формулу и APFU"
    if st.button(button_label, type="primary", key="workflow_formula", width="stretch"):
        st.session_state["workflow_formula_dataset_id"] = int(dataset["id"])
        st.session_state["workflow_formula_method_id"] = method.id
        st.session_state.pop("formula_dataset", None)
        st.session_state.pop("formula_method", None)
        _jump("formulae")


def _context_step(project_id: int, dataset: dict) -> None:
    render_section_header("5 · Фото, шлиф и физическая точка", "Связать химию с тем, что вы действительно видели")
    images = list_dataset_images(int(dataset["id"]))
    render_badges([(f"изображений · {len(images)}", "accent" if images else "neutral")])
    st.caption(
        "BSE/EDS/фото можно связать с одной или несколькими аналитическими строками. Шлиф хранит поля и координаты; одна физическая точка может объединять EPMA, EDS и LA, не смешивая сами измерения."
    )
    c1, c2, c3 = st.columns(3)
    if c1.button("Изображения", type="primary" if not images else "secondary", key="workflow_images", width="stretch"):
        st.session_state["workflow_image_dataset_id"] = int(dataset["id"])
        _jump("images")
    if c2.button("Шлифы и карта точек", key="workflow_slides", width="stretch"):
        _jump("slides")
    if c3.button("Точки / кратеры / навески", key="workflow_measurements", width="stretch"):
        _jump("measurements")

    st.caption("Морфология — наблюдение; Generation — интерпретация. Их можно добавить после изображения, когда видно ядро, кайму, включение и текстурную позицию.")
    m1, m2 = st.columns(2)
    if m1.button("Морфология в сессии", key="workflow_morphology", width="stretch"):
        _jump("sessions")
    if m2.button("Поколения / Generation", key="workflow_generation", width="stretch"):
        _jump("generations")


def _plot_step(dataset: dict) -> None:
    render_section_header("6 · Исследовать", "Открыть тот же dataset в графиках или статистике")
    st.caption("Selection, QC, Hide и Exclude сохраняют свои отдельные роли; смена представления не расширяет область данных молча.")
    c1, c2 = st.columns(2)
    if c1.button("Построить XY", type="primary", key="workflow_plot", width="stretch"):
        st.session_state["workflow_plot_dataset_ids"] = [int(dataset["id"])]
        st.session_state.pop("quick_plot_datasets", None)
        _jump("plots")
    if c2.button("Статистика / PCA / группы", key="workflow_stats", width="stretch"):
        st.session_state["statistics_dataset_ids_pending"] = [int(dataset["id"])]
        st.session_state.pop("statistics_datasets", None)
        _jump("statistics")


def render_guided_workflow_page() -> None:
    project = active_project()
    render_page_header(
        "Рабочий процесс",
        "От зонда или LA-файла до проверенных фаз, APFU, Sample, изображений, шлифов и первого графика — без необходимости помнить структуру PetroLab.",
        eyebrow="Данные",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        if st.button("Проекты", type="primary", key="workflow_projects"):
            _jump("projects")
        return

    project_id = int(project["id"])
    st.caption(
        "Порядок не блокирующий: любой шаг можно пропустить и вернуться позже. PetroLab предупреждает о недостающем контексте, но не запрещает смотреть данные или строить графики."
    )
    _session_summary(project_id)
    dataset, _ = _dataset_selector(project_id)
    if dataset is None:
        return
    _dataset_session_context(project_id, dataset)
    _phase_step(dataset)
    _formula_step(dataset)
    _context_step(project_id, dataset)
    _plot_step(dataset)
