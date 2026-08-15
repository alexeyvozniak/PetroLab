from __future__ import annotations

from pathlib import Path

import streamlit as st

from petrolab.repositories.rock_repository import list_rocks
from petrolab.rock_workspace_model import (
    major_composition_table,
    rock_workspace_snapshot,
    trace_composition_table,
)
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project
from petrolab.ui.rock_plots import render_rock_plots


def _rock_label(rock: dict) -> str:
    values = [
        str(rock.get("name") or ""),
        str(rock.get("massif") or ""),
        str(rock.get("lithology") or ""),
    ]
    return " · ".join(value for value in values if value.strip())


def _go(route: str) -> None:
    navigate(route)
    st.rerun()


def render_rock_workspace_page() -> None:
    project = active_project()
    if project is None:
        render_page_header(
            "Породы",
            "Образцы, валовая химия, trace elements, изотопия, фотографии и связанные минералогические данные.",
            eyebrow="Материалы",
            context="Проект не выбран",
        )
        st.info("Сначала создайте или выберите проект.")
        return

    project_id = int(project["id"])
    rocks = list_rocks(project_id)
    if not rocks:
        render_page_header(
            "Породы",
            "Образцы, валовая химия, trace elements, изотопия, фотографии и связанные минералогические данные.",
            eyebrow="Материалы",
            context=str(project["name"]),
        )
        st.info("В проекте пока нет пород. Добавьте первую вручную или импортируйте whole-rock таблицу.")
        if st.button("Открыть редактор / импорт пород", type="primary", width="stretch"):
            _go("rocks")
        return

    by_id = {int(rock["id"]): rock for rock in rocks}
    pending_id = st.session_state.pop("rock_workspace_open_id", None)
    default_id = int(pending_id) if pending_id is not None and int(pending_id) in by_id else next(iter(by_id))
    rock_id = st.selectbox(
        "Открыть образец",
        list(by_id),
        index=list(by_id).index(default_id),
        format_func=lambda value: _rock_label(by_id[int(value)]),
        key="rock_workspace_select",
    )
    try:
        snapshot = rock_workspace_snapshot(project_id, int(rock_id))
    except Exception as exc:
        st.error(f"Не удалось открыть породу: {exc}")
        return
    rock = snapshot.rock

    age = ""
    if rock.get("age_ma") is not None:
        age = f"{float(rock['age_ma']):g} Ma"
        if rock.get("age_uncertainty_ma") is not None:
            age += f" ± {float(rock['age_uncertainty_ma']):g}"
    subtitle_parts = [
        str(rock.get("lithology") or "").strip(),
        str(rock.get("massif") or "").strip(),
        str(rock.get("locality") or "").strip(),
        age,
    ]
    render_page_header(
        str(rock["name"]),
        " · ".join(value for value in subtitle_parts if value),
        eyebrow="Порода / образец",
        context=str(project["name"]),
    )

    badges = [
        (f"major · {snapshot.major_present}/{snapshot.major_expected}", "success" if snapshot.major_fraction >= 0.9 else "warning"),
        (f"trace · {snapshot.trace_count}", "success" if snapshot.trace_count else "neutral"),
        (f"изотопные системы · {len(snapshot.isotope_systems)}", "accent" if snapshot.isotope_systems else "neutral"),
        (f"mineral datasets · {len(snapshot.linked_datasets)}", "accent" if snapshot.linked_datasets else "neutral"),
        (f"фото · {len(snapshot.images)}", "neutral"),
    ]
    render_badges(badges)

    q1, q2, q3 = st.columns(3)
    if q1.button("Сравнить с литературой", type="primary", width="stretch", key="rock_workspace_compare"):
        st.session_state["whole_rock_workspace_rock_ids"] = [int(rock_id)]
        _go("whole_rock_compare")
    if q2.button("Диаграммы этой породы", width="stretch", key="rock_workspace_plots_jump"):
        st.session_state["rock_workspace_tab"] = "Диаграммы"
        st.rerun()
    if q3.button("Редактировать / добавить данные", width="stretch", key="rock_workspace_edit"):
        st.session_state["rock_workspace_edit_id"] = int(rock_id)
        _go("rocks")

    tab_names = [
        "Обзор", "Валовая химия", "Trace elements", "Изотопия",
        "Минералы", "Фото", "Диаграммы", "Происхождение",
    ]
    tabs = st.tabs(tab_names)

    with tabs[0]:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Основные компоненты", f"{snapshot.major_present}/{snapshot.major_expected}")
        m2.metric("Trace elements", snapshot.trace_count)
        m3.metric("Изотопные системы", len(snapshot.isotope_systems))
        m4.metric("Связанные datasets", len(snapshot.linked_datasets))

        render_section_header("Паспорт", "Главное об образце без входа в форму редактирования")
        passport = {
            "Массив / комплекс": rock.get("massif") or "—",
            "Литология": rock.get("lithology") or "—",
            "Местоположение": rock.get("locality") or "—",
            "Возраст": age or "—",
            "Метод возраста": rock.get("age_method") or "—",
            "Лаборатория": rock.get("laboratory") or "—",
        }
        left, right = st.columns(2)
        items = list(passport.items())
        for index, (label, value) in enumerate(items):
            (left if index % 2 == 0 else right).markdown(f"**{label}:** {value}")
        description = str(rock.get("description") or "").strip()
        if description:
            st.markdown(f"**Описание:** {description}")

        render_section_header("Качество данных", "Что уже достаточно для интерпретации, а что стоит дополнить")
        if snapshot.warnings:
            for warning in snapshot.warnings:
                st.warning(warning)
        else:
            st.success("По базовым проверкам карточка породы заполнена полно.")

    with tabs[1]:
        major = major_composition_table(snapshot)
        if major.empty:
            st.info("Основные компоненты не добавлены.")
        else:
            st.dataframe(major, width="stretch", hide_index=True)
        st.caption("Редактирование остаётся в техническом редакторе; этот экран предназначен для чтения и интерпретации.")

    with tabs[2]:
        traces = trace_composition_table(snapshot)
        if traces.empty:
            st.info("Распознанных trace-element концентраций пока нет.")
        else:
            st.dataframe(traces, width="stretch", hide_index=True)
            st.caption("Единицы отображаются из канонического whole-rock хранилища; wt.% и µg/g не объединяются автоматически.")

    with tabs[3]:
        if snapshot.isotopes.empty:
            st.info("Изотопные определения не добавлены.")
        else:
            st.dataframe(snapshot.isotopes, width="stretch", hide_index=True)
            if snapshot.isotope_systems:
                st.caption("Системы: " + ", ".join(snapshot.isotope_systems))

    with tabs[4]:
        if not snapshot.linked_datasets:
            st.info("С этой породой пока не связаны минералогические datasets.")
        else:
            for dataset in snapshot.linked_datasets:
                st.markdown(
                    f"**{dataset['name']}** · {dataset.get('mineral_key') or 'generic'} · "
                    f"{int(dataset.get('row_count') or 0)} анализов · {dataset.get('source_filename') or ''}"
                )
        if st.button("Изменить связи минерал–порода", key="rock_workspace_edit_links"):
            st.session_state["rock_workspace_edit_id"] = int(rock_id)
            _go("rocks")

    with tabs[5]:
        if not snapshot.images:
            st.info("Общих фотографий породы нет.")
        else:
            columns = st.columns(min(3, len(snapshot.images)))
            for index, image in enumerate(snapshot.images):
                path = Path(str(image.get("stored_path") or ""))
                with columns[index % len(columns)]:
                    if path.is_file():
                        st.image(
                            str(path),
                            caption=str(image.get("title") or image.get("original_filename") or path.name),
                            width="stretch",
                        )
                    else:
                        st.warning(f"Файл недоступен: {image.get('original_filename') or image.get('id')}")

    with tabs[6]:
        render_rock_plots(project_id, rock)

    with tabs[7]:
        render_section_header("Методы и источники", "Provenance whole-rock данных")
        st.markdown("**Методы химии:** " + (", ".join(snapshot.chemistry_methods) if snapshot.chemistry_methods else "—"))
        st.markdown("**Источники химии:** " + (", ".join(snapshot.chemistry_sources) if snapshot.chemistry_sources else "—"))
        st.markdown(f"**Метод изотопии в паспорте:** {rock.get('isotope_method') or '—'}")
        st.markdown(f"**Лаборатория:** {rock.get('laboratory') or '—'}")
        notes = str(rock.get("notes") or "").strip()
        st.markdown("**Заметки:** " + (notes if notes else "—"))
