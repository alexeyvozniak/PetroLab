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
    list_sessions,
    sample_history,
    session_datasets,
    set_annotations,
    update_session_status,
)
from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.sample_registry import create_sample, find_sample_matches, list_samples
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project_id

ZONE_OPTIONS = ["", "core", "intermediate", "rim", "overgrowth", "inclusion", "unknown"]
SIZE_OPTIONS = ["", "small", "medium", "large", "unknown"]
TEXTURE_OPTIONS = ["", "phenocryst", "antecryst", "xenocryst", "groundmass", "inclusion", "reaction zone", "unknown"]


def _jump(route: str) -> None:
    st.session_state["nav_route"] = route
    st.rerun()


def _sample_selector(project_id: int) -> tuple[int | None, str]:
    samples = list_samples(project_id)
    options = [0] + [int(row["id"]) for row in samples]
    by_id = {int(row["id"]): row for row in samples}
    selected = st.selectbox(
        "Образец",
        options,
        format_func=lambda value: "＋ Новый образец" if value == 0 else str(by_id[int(value)]["name"]),
        key="session_sample_choice",
    )
    if selected:
        return int(selected), str(by_id[int(selected)]["name"])

    proposed = st.text_input("Название нового образца", key="session_new_sample", placeholder="например, PG-15")
    if not proposed.strip():
        return None, ""
    matches = find_sample_matches(project_id, proposed)
    if matches:
        st.warning("Похожий образец уже есть. PetroLab не объединяет их автоматически.")
        match_options = [match.sample_id for match in matches]
        match_by_id = {match.sample_id: match for match in matches}
        existing = st.radio(
            "Использовать существующий образец?",
            match_options + [0],
            format_func=lambda value: "Нет, это новый образец" if value == 0 else f"{match_by_id[value].canonical_name} · совпадение: {match_by_id[value].match_kind}",
            key="session_duplicate_choice",
        )
        if existing:
            return int(existing), str(match_by_id[int(existing)].canonical_name)
    return None, proposed.strip()


def _create_session_block(project_id: int) -> None:
    with st.expander("Новая аналитическая сессия", expanded=not bool(list_sessions(project_id))):
        st.caption("Одна сессия может содержать несколько минералов и файлов. Повторные измерения сохраняются отдельной сессией того же Sample.")
        sample_id, sample_name = _sample_selector(project_id)
        c1, c2 = st.columns(2)
        session_date = c1.date_input("Дата измерений", value=date.today(), key="session_new_date")
        technique = c2.selectbox("Метод", list(TECHNIQUES), format_func=lambda value: TECHNIQUES[value], key="session_new_technique")
        session_name = st.text_input("Название сессии · необязательно", key="session_new_name")
        with st.expander("Лаборатория и прибор · необязательно", expanded=False):
            d1, d2 = st.columns(2)
            facility = d1.text_input("Где сделано / лаборатория", key="session_new_facility")
            instrument = d2.text_input("Прибор", key="session_new_instrument")
            d3, d4 = st.columns(2)
            mode = d3.text_input("Режим / детектор", key="session_new_mode")
            operator = d4.text_input("Оператор", key="session_new_operator")
            tags_text = st.text_input("Дополнительные метки", key="session_new_tags", placeholder="через запятую")
            notes = st.text_area("Заметка", key="session_new_notes", height=80)

        can_create = bool(sample_name.strip())
        if st.button("Создать сессию", type="primary", disabled=not can_create, key="create_analytical_session"):
            resolved_sample_id = sample_id
            if resolved_sample_id is None:
                matches = find_sample_matches(project_id, sample_name)
                if matches:
                    st.error("Для похожего названия сначала подтвердите, новый это Sample или существующий.")
                    return
                resolved_sample_id = create_sample(project_id, sample_name)
            session_id = create_session(
                project_id,
                int(resolved_sample_id),
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
            st.success("Аналитическая сессия создана.")
            st.rerun()


def _session_header(session: dict) -> None:
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
    candidates = [item for item in list_accessible_datasets(project_id) if int(item["id"]) not in linked_ids]
    if linked:
        st.dataframe(pd.DataFrame([{
            "Набор": item["name"], "Минерал": item["mineral_key"], "Источник": item["source_filename"],
            "Лист": item["source_sheet"], "Анализов": item["row_count"],
        } for item in linked]), width="stretch", hide_index=True)
    else:
        st.info("Импортируйте файл, затем привяжите созданные mineral datasets к этой сессии.")
    if candidates:
        labels = {f"{item['name']} · {item['mineral_key']} · {item['source_filename']} · {item['row_count']} анализов": int(item["id"]) for item in candidates}
        selected = st.multiselect("Добавить импортированные наборы", list(labels), key=f"session_attach_{session_id}")
        if st.button("Привязать выбранные наборы", disabled=not selected, key=f"session_attach_btn_{session_id}"):
            try:
                attach_datasets(session_id, [labels[label] for label in selected])
                st.success("Наборы добавлены в сессию.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
    minerals = sorted({str(item.get("mineral_key", "")) for item in linked if item.get("mineral_key")})
    if minerals:
        st.caption("Минералы в сессии: " + ", ".join(minerals))
    return linked


def _morphology_step(project_id: int, session_id: int, linked: list[dict]) -> None:
    st.markdown("### 4 · Морфология")
    if not linked:
        st.caption("Сначала привяжите наборы с анализами.")
        return
    dataframe = load_unified_with_derived(project_id, [int(item["id"]) for item in linked])
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        return
    st.caption("Morphology хранится отдельно от Generation: сначала фиксируем наблюдение, интерпретировать его можно позже.")
    label_columns = [column for column in ["Sample", "Grain", "Point", "Минерал", "Generation"] if column in dataframe.columns]
    def point_label(row: pd.Series) -> str:
        bits = [str(row.get(column, "")).strip() for column in label_columns if str(row.get(column, "")).strip()]
        return " · ".join(bits) + f" · {str(row['_analysis_id'])[:8]}"
    point_map = {point_label(row): str(row["_analysis_id"]) for _, row in dataframe.head(5000).iterrows()}
    selected_labels = st.multiselect("Точки для разметки", list(point_map), key=f"session_morph_points_{session_id}")
    if selected_labels:
        c1, c2, c3 = st.columns(3)
        zone = c1.selectbox(MORPHOLOGY_KEYS["zone"], ZONE_OPTIONS, key=f"session_zone_{session_id}")
        size = c2.selectbox(MORPHOLOGY_KEYS["grain_size"], SIZE_OPTIONS, key=f"session_size_{session_id}")
        texture = c3.selectbox(MORPHOLOGY_KEYS["textural_role"], TEXTURE_OPTIONS, key=f"session_texture_{session_id}")
        note = st.text_input(MORPHOLOGY_KEYS["note"], key=f"session_morph_note_{session_id}")
        values = {key: value for key, value in {"zone": zone, "grain_size": size, "textural_role": texture, "note": note}.items() if value}
        if st.button("Применить", type="primary", disabled=not values, key=f"session_morph_apply_{session_id}"):
            changed = set_annotations([point_map[label] for label in selected_labels], values)
            st.success(f"Разметка сохранена для {changed} анализов.")
            st.rerun()
    annotations = annotation_table(dataframe["_analysis_id"].astype(str).tolist())
    if annotations:
        with st.expander(f"Размеченные точки · {len(annotations)}", expanded=False):
            st.dataframe(pd.DataFrame([{"analysis_id": aid, **values} for aid, values in annotations.items()]), width="stretch", hide_index=True)


def _finish_step(session: dict) -> None:
    st.markdown("### 6 · Статус")
    current = str(session.get("status", "draft"))
    choice = st.segmented_control("Состояние", list(SESSION_STATUSES), default=current, format_func=lambda value: SESSION_STATUSES[value], key=f"session_status_{session['id']}")
    if choice and choice != current:
        update_session_status(int(session["id"]), str(choice))
        st.rerun()
    st.caption("Разбор → Проверка → Готово. Статус не блокирует последующее редактирование.")


def render_analytical_sessions_page() -> None:
    render_page_header(
        "Аналитические сессии",
        "Зонд, EDS и LA-ICP-MS: один понятный путь от нового файла до привязанных минералов, фотографий и морфологии.",
        eyebrow="Данные",
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
    session_id = st.selectbox("Текущая сессия", ids, index=ids.index(default_id), format_func=lambda value: f"{by_id[int(value)]['sample_name']} · {by_id[int(value)]['name']}", key="analytical_session_selector")
    st.session_state["active_analytical_session"] = int(session_id)
    session = by_id[int(session_id)]
    _session_header(session)
    linked = _dataset_step(project_id, int(session_id))
    _morphology_step(project_id, int(session_id), linked)
    _finish_step(session)
    with st.expander("История образца", expanded=False):
        history = sample_history(project_id, int(session["sample_id"]))
        st.dataframe(pd.DataFrame([{
            "Дата": item["session_date"], "Сессия": item["name"], "Метод": TECHNIQUES.get(item["technique"], item["technique"]),
            "Наборов": item["dataset_count"], "Анализов": item["analysis_count"], "Статус": SESSION_STATUSES.get(item["status"], item["status"]),
        } for item in history["sessions"]]), width="stretch", hide_index=True)
