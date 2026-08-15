from __future__ import annotations

import math
from pathlib import Path

import streamlit as st

from petrolab.repositories.rock_repository import list_rocks, update_rock
from petrolab.rock_workspace_export import rock_sample_card_json_bytes, rock_sample_card_xlsx_bytes
from petrolab.rock_workspace_model import major_composition_table, rock_workspace_snapshot, trace_composition_table
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project
from petrolab.ui.rock_plots import render_rock_plots


def _rock_label(rock: dict) -> str:
    values = [str(rock.get("name") or ""), str(rock.get("massif") or ""), str(rock.get("lithology") or "")]
    return " · ".join(value for value in values if value.strip())


def _go(route: str) -> None:
    navigate(route)
    st.rerun()


def _age_label(rock: dict) -> str:
    try:
        age_value = float(rock.get("age_ma"))
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(age_value):
        return ""
    text = f"{age_value:g} Ma"
    try:
        uncertainty = float(rock.get("age_uncertainty_ma"))
    except (TypeError, ValueError):
        uncertainty = float("nan")
    if math.isfinite(uncertainty):
        text += f" ± {uncertainty:g}"
    return text


def _valid_rock_id(value, by_id: dict[int, dict]) -> int | None:
    try:
        rock_id = int(value)
    except (TypeError, ValueError):
        return None
    return rock_id if rock_id in by_id else None


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
        if st.button("Открыть редактор / импорт пород", type="primary", width="stretch", key=f"rock_workspace_empty_edit_{project_id}"):
            _go("rocks")
        return

    by_id = {int(rock["id"]): rock for rock in rocks}
    selector_key = f"rock_workspace_select_{project_id}"
    pending_id = _valid_rock_id(st.session_state.pop("rock_workspace_open_id", None), by_id)
    if pending_id is not None:
        st.session_state[selector_key] = pending_id
    current_id = _valid_rock_id(st.session_state.get(selector_key), by_id)
    if current_id is None:
        st.session_state[selector_key] = next(iter(by_id))
    rock_id = st.selectbox(
        "Открыть образец",
        list(by_id),
        format_func=lambda value: _rock_label(by_id[int(value)]),
        key=selector_key,
    )
    try:
        snapshot = rock_workspace_snapshot(project_id, int(rock_id))
    except Exception as exc:
        st.error(f"Не удалось открыть породу: {exc}")
        return
    rock = snapshot.rock

    age = _age_label(rock)
    subtitle_parts = [str(rock.get("lithology") or "").strip(), str(rock.get("massif") or "").strip(), str(rock.get("locality") or "").strip(), age]
    render_page_header(
        str(rock["name"]),
        " · ".join(value for value in subtitle_parts if value),
        eyebrow="Порода / образец",
        context=str(project["name"]),
    )

    render_badges([
        (f"major · {snapshot.major_present}/{snapshot.major_expected}", "success" if snapshot.major_fraction >= 0.9 else "warning"),
        (f"trace · {snapshot.trace_count}", "success" if snapshot.trace_count else "neutral"),
        (f"изотопные системы · {len(snapshot.isotope_systems)}", "accent" if snapshot.isotope_systems else "neutral"),
        (f"mineral datasets · {len(snapshot.linked_datasets)}", "accent" if snapshot.linked_datasets else "neutral"),
        (f"фото · {len(snapshot.images)}", "neutral"),
    ])

    q1, q2, q3 = st.columns([2, 2, 1])
    if q1.button("Сравнить / построить whole-rock диаграммы", type="primary", width="stretch", key=f"rock_workspace_compare_{project_id}"):
        st.session_state["whole_rock_workspace_context"] = {
            "project_id": project_id,
            "rock_ids": [int(rock_id)],
            "label": str(rock.get("name") or rock_id),
        }
        st.session_state["whole_rock_workspace_rock_ids"] = [int(rock_id)]
        _go("whole_rock_compare")
    if q2.button("Редактировать / добавить данные", width="stretch", key=f"rock_workspace_edit_{project_id}"):
        st.session_state["rock_workspace_edit_id"] = int(rock_id)
        _go("rocks")
    with q3.popover("Экспорт карточки", width="stretch"):
        safe_name = str(rock.get("name") or f"rock-{rock_id}").replace("/", "_").replace("\\", "_")
        st.download_button(
            "XLSX",
            rock_sample_card_xlsx_bytes(snapshot),
            file_name=f"{safe_name}_PetroLab.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch",
            key=f"rock_workspace_export_xlsx_{project_id}_{rock_id}",
        )
        st.download_button(
            "JSON",
            rock_sample_card_json_bytes(snapshot),
            file_name=f"{safe_name}_PetroLab.json",
            mime="application/json",
            width="stretch",
            key=f"rock_workspace_export_json_{project_id}_{rock_id}",
        )
        st.caption("Экспорт содержит паспорт, chemistry с per-analyte provenance, isotopes, data health, mineral links и список изображений.")

    tabs = st.tabs([
        "Обзор", "Валовая химия", "Trace elements", "Изотопия",
        "Минералы", "Фото", "Диаграммы", "Интерпретация", "Происхождение",
    ])

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
        for index, (label, value) in enumerate(passport.items()):
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
                st.caption("Системы с конечными определениями: " + ", ".join(snapshot.isotope_systems))

    with tabs[4]:
        if not snapshot.linked_datasets:
            st.info("С этой породой пока не связаны доступные минералогические datasets.")
        else:
            for dataset in snapshot.linked_datasets:
                membership = " · из общей базы" if bool(dataset.get("linked_to_project")) else ""
                st.markdown(
                    f"**{dataset['name']}** · {dataset.get('mineral_key') or 'generic'} · "
                    f"{int(dataset.get('row_count') or 0)} анализов · {dataset.get('source_filename') or ''}{membership}"
                )
        if st.button("Изменить связи минерал–порода", key=f"rock_workspace_edit_links_{project_id}"):
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
                        st.image(str(path), caption=str(image.get("title") or image.get("original_filename") or path.name), width="stretch")
                    else:
                        st.warning(f"Файл недоступен: {image.get('original_filename') or image.get('id')}")

    with tabs[6]:
        render_rock_plots(project_id, rock)

    with tabs[7]:
        render_section_header("Интерпретация", "Рабочий геологический текст, отделённый от исходных измерений")
        with st.form(f"rock_workspace_interpretation_{project_id}_{rock_id}"):
            description = st.text_area("Описание образца / петрография", value=str(rock.get("description") or ""), height=150)
            notes = st.text_area(
                "Интерпретация и рабочие заметки",
                value=str(rock.get("notes") or ""),
                height=220,
                help="Здесь хранится интерпретационный текст. Химические и изотопные строки при сохранении не изменяются.",
            )
            if st.form_submit_button("Сохранить интерпретацию", type="primary"):
                try:
                    update_rock(int(rock_id), description=description, notes=notes)
                except Exception as exc:
                    st.error(f"Не удалось сохранить интерпретацию: {exc}")
                else:
                    st.success("Интерпретация сохранена.")
                    st.rerun()
        st.caption("Измеренные значения, units, methods и sources редактируются отдельно и не переписываются этой вкладкой.")

    with tabs[8]:
        render_section_header("Методы и источники", "Provenance whole-rock данных")
        st.markdown("**Методы химии:** " + (", ".join(snapshot.chemistry_methods) if snapshot.chemistry_methods else "—"))
        st.markdown("**Источники химии:** " + (", ".join(snapshot.chemistry_sources) if snapshot.chemistry_sources else "—"))
        st.markdown(f"**Метод изотопии в паспорте:** {rock.get('isotope_method') or '—'}")
        st.markdown(f"**Лаборатория:** {rock.get('laboratory') or '—'}")
        notes = str(rock.get("notes") or "").strip()
        st.markdown("**Рабочие заметки:** " + (notes if notes else "—"))
