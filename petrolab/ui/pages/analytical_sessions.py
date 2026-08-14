from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from petrolab.analytical_sessions import (
    MORPHOLOGY_KEYS,
    SESSION_STATUSES,
    TECHNIQUES,
    annotation_table,
    attach_datasets,
    create_session,
    get_or_create_sample,
    list_samples,
    list_sessions,
    sample_history,
    session_datasets,
    set_annotations,
    update_session_status,
)
from petrolab.db import list_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project_id


ZONE_OPTIONS = ["", "core", "intermediate", "rim", "overgrowth", "inclusion", "unknown"]
SIZE_OPTIONS = ["", "small", "medium", "large", "unknown"]
TEXTURE_OPTIONS = ["", "phenocryst", "antecryst", "xenocryst", "groundmass", "inclusion", "reaction zone", "unknown"]


def _jump(route: str) -> None:
    st.session_state["nav_route"] = route
    st.rerun()


def _create_session_block(project_id: int) -> None:
    with st.expander("Новая аналитическая сессия", expanded=not bool(list_sessions(project_id))):
        st.caption("Одна сессия может содержать несколько минералов и несколько исходных файлов. Повторные измерения того же образца сохраняются отдельной сессией внутри одного Sample.")
        c1, c2 = st.columns([1.1, 1.0])
        sample_name = c1.text_input("Образец", key="session_new_sample", placeholder="например, PG-15")
        session_date = c2.date_input("Дата измерений", value=date.today(), key="session_new_date")
        c3, c4 = st.columns(2)
        technique = c3.selectbox("Метод", list(TECHNIQUES), format_func=lambda value: TECHNIQUES[value], key="session_new_technique")
        session_name = c4.text_input("Название сессии · необязательно", key="session_new_name")
        with st.expander("Лаборатория и прибор · необязательно", expanded=False):
            d1, d2 = st.columns(2)
            facility = d1.text_input("Где сделано / лаборатория", key="session_new_facility", placeholder="ИГЕМ РАН, МГУ, ...")
            instrument = d2.text_input("Прибор", key="session_new_instrument", placeholder="JEOL JXA-8230, Element XR, ...")
            d3, d4 = st.columns(2)
            mode = d3.text_input("Режим / детектор", key="session_new_mode", placeholder="WDS, EDS, spot 40 µm, ...")
            operator = d4.text_input("Оператор", key="session_new_operator")
            tags_text = st.text_input("Дополнительные метки", key="session_new_tags", placeholder="через запятую")
            notes = st.text_area("Заметка", key="session_new_notes", height=80)
        if st.button("Создать сессию", type="primary", disabled=not sample_name.strip(), key="create_analytical_session"):
            sample_id, created = get_or_create_sample(project_id, sample_name)
            session_id = create_session(
                project_id,
                sample_id,
                name=session_name,
                session_date=session_date,
                technique=technique,
                facility=facility,
                instrument=instrument,
                operator=operator,
                mode=mode,
                notes=notes,
                tags=[part.strip() for part in tags_text.split(",") if part.strip()],
            )
            st.session_state["active_analytical_session"] = session_id
            st.success(("Создан новый образец и сессия." if created else "Образец уже существовал; добавлена новая сессия."))
            st.rerun()


def _session_header(project_id: int, session: dict) -> None:
    technique = TECHNIQUES.get(str(session.get("technique")), str(session.get("technique", "")))
    status = str(session.get("status", "draft"))
    render_badges([
        (str(session.get("sample_name", "")), "accent"),
        (technique, "neutral"),
        (str(session.get("session_date") or "без даты"), "neutral"),
        (SESSION_STATUSES.get(status, status), "neutral"),
    ])
    caption = " · ".join(value for value in [str(session.get("facility", "")), str(session.get("instrument", "")), str(session.get("mode", ""))] if value)
    if caption:
        st.caption(caption)
    c1, c2, c3 = st.columns(3)
    if c1.button("1 · Импорт данных", width="stretch"):
        _jump("sources")
    if c2.button("2 · Изображения", width="stretch"):
        _jump("images")
    if c3.button("5 · Статистика / PCA", width="stretch"):
        _jump("statistics")


def _dataset_step(project_id: int, session_id: int) -> list[dict]:
    st.markdown("### 3 · Данные сессии")
    linked = session_datasets(session_id)
    linked_ids = {int(item["id"]) for item in linked}
    all_datasets = list_datasets(project_id)
    candidates = [item for item in all_datasets if int(item["id"]) not in linked_ids]
    if linked:
        view = pd.DataFrame([
            {
                "Набор": item["name"],
                "Минерал": item["mineral_key"],
                "Источник": item["source_filename"],
                "Лист": item["source_sheet"],
                "Анализов": item["row_count"],
            }
            for item in linked
        ])
        st.dataframe(view, width="stretch", hide_index=True)
    else:
        st.info("К сессии пока не привязано ни одного набора. Импортируйте файл обычным импортом, затем отметьте созданные наборы здесь.")
    if candidates:
        labels = {
            f"{item['name']} · {item['mineral_key']} · {item['source_filename']} · {item['row_count']} анализов": int(item["id"])
            for item in candidates
        }
        selected = st.multiselect("Добавить уже импортированные наборы в эту сессию", list(labels), key=f"session_attach_{session_id}")
        if st.button("Привязать выбранные наборы", disabled=not selected, key=f"session_attach_btn_{session_id}"):
            attach_datasets(session_id, [labels[label] for label in selected])
            st.success("Наборы добавлены в сессию.")
            st.rerun()
    minerals = sorted({str(item.get("mineral_key", "")) for item in linked if item.get("mineral_key")})
    if minerals:
        st.caption("Минералы в сессии: " + ", ".join(minerals))
    return linked


def _morphology_step(project_id: int, session_id: int, linked: list[dict]) -> None:
    st.markdown("### 4 · Быстрая морфологическая разметка")
    if not linked:
        st.caption("Сначала привяжите наборы с анализами.")
        return
    dataset_ids = [int(item["id"]) for item in linked]
    dataframe = load_unified_with_derived(project_id, dataset_ids)
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        st.caption("В сессии пока нет аналитических строк.")
        return
    st.caption("Это наблюдения, а не интерпретация поколения: core/rim, размер зерна и текстурная позиция сохраняются отдельно от Generation.")
    label_columns = [column for column in ["Sample", "Grain", "Point", "Минерал", "Generation", "Источник", "Лист"] if column in dataframe.columns]
    def point_label(row: pd.Series) -> str:
        bits = [str(row.get(column, "")).strip() for column in label_columns if str(row.get(column, "")).strip()]
        return " · ".join(bits) + f" · {str(row['_analysis_id'])[:8]}"
    limit = min(5000, len(dataframe))
    point_map = {point_label(row): str(row["_analysis_id"]) for _, row in dataframe.head(limit).iterrows()}
    selected_labels = st.multiselect("Выберите точки для разметки", list(point_map), key=f"session_morph_points_{session_id}")
    if selected_labels:
        c1, c2, c3 = st.columns(3)
        zone = c1.selectbox(MORPHOLOGY_KEYS["zone"], ZONE_OPTIONS, key=f"session_zone_{session_id}")
        grain_size = c2.selectbox(MORPHOLOGY_KEYS["grain_size"], SIZE_OPTIONS, key=f"session_size_{session_id}")
        texture = c3.selectbox(MORPHOLOGY_KEYS["textural_role"], TEXTURE_OPTIONS, key=f"session_texture_{session_id}")
        note = st.text_input(MORPHOLOGY_KEYS["note"], key=f"session_morph_note_{session_id}")
        values = {"zone": zone, "grain_size": grain_size, "textural_role": texture, "note": note}
        values = {key: value for key, value in values.items() if value}
        if st.button("Применить к выбранным", type="primary", disabled=not values, key=f"session_morph_apply_{session_id}"):
            changed = set_annotations([point_map[label] for label in selected_labels], values)
            st.success(f"Разметка сохранена для {changed} анализов.")
            st.rerun()
    ids = dataframe["_analysis_id"].astype(str).tolist()
    annotations = annotation_table(ids)
    if annotations:
        rows = []
        meta = dataframe.set_index(dataframe["_analysis_id"].astype(str))
        for analysis_id, values in annotations.items():
            row = {"analysis_id": analysis_id}
            if analysis_id in meta.index:
                source = meta.loc[analysis_id]
                for column in ["Sample", "Grain", "Point", "Минерал", "Generation"]:
                    if column in dataframe.columns:
                        row[column] = source.get(column, "")
            row.update(values)
            rows.append(row)
        with st.expander(f"Размеченные точки · {len(rows)}", expanded=False):
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=320)


def _finish_step(session: dict) -> None:
    st.markdown("### 6 · Статус сессии")
    current = str(session.get("status", "draft"))
    labels = list(SESSION_STATUSES)
    choice = st.segmented_control(
        "Состояние",
        labels,
        default=current if current in labels else "draft",
        format_func=lambda value: SESSION_STATUSES[value],
        key=f"session_status_{session['id']}",
    )
    if choice and choice != current:
        update_session_status(int(session["id"]), str(choice))
        st.success("Статус обновлён.")
        st.rerun()
    st.caption("`Разбор` — сырые данные и рабочие гипотезы; `Проверка` — генерации и расчёты проверяются; `Готово` — сессия считается разобранной. Данные при этом остаются редактируемыми.")


def render_analytical_sessions_page() -> None:
    render_page_header(
        "Аналитические сессии",
        "Простой путь от свежего зондового или лазерного файла до фотографий, морфологии, рабочих групп, статистики и проверенных поколений.",
        eyebrow="Лаборатория",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала выберите или создайте проект.")
        return
    project_id = int(project_id)
    _create_session_block(project_id)
    sessions = list_sessions(project_id)
    if not sessions:
        return
    by_id = {int(item["id"]): item for item in sessions}
    default_id = int(st.session_state.get("active_analytical_session", sessions[0]["id"]))
    if default_id not in by_id:
        default_id = int(sessions[0]["id"])
    ids = list(by_id)
    session_id = st.selectbox(
        "Текущая сессия",
        ids,
        index=ids.index(default_id),
        format_func=lambda value: f"{by_id[int(value)]['sample_name']} · {by_id[int(value)]['name']}",
        key="analytical_session_selector",
    )
    st.session_state["active_analytical_session"] = int(session_id)
    session = by_id[int(session_id)]
    _session_header(project_id, session)
    linked = _dataset_step(project_id, int(session_id))
    _morphology_step(project_id, int(session_id), linked)
    _finish_step(session)

    with st.expander("История образца", expanded=False):
        history = sample_history(project_id, int(session["sample_id"]))
        rows = []
        for item in history["sessions"]:
            rows.append({
                "Дата": item["session_date"],
                "Сессия": item["name"],
                "Метод": TECHNIQUES.get(item["technique"], item["technique"]),
                "Наборов": item["dataset_count"],
                "Анализов": item["analysis_count"],
                "Статус": SESSION_STATUSES.get(item["status"], item["status"]),
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
