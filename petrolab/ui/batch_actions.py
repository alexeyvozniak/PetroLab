from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analytical_sessions import MORPHOLOGY_KEYS
from petrolab.operation_journal import (
    assign_generation_with_journal,
    reassign_phase_with_journal,
    set_annotation_with_journal,
)
from petrolab.ui.layout import render_badges, render_section_header
from petrolab.ui.navigation import navigate


def _selection_editor(dataframe: pd.DataFrame, project_id: int) -> list[str]:
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        return []
    scope = st.segmented_control(
        "К каким точкам применить действие",
        ["Весь текущий отбор", "Выбрать строки"],
        default="Весь текущий отбор",
        key=f"batch_scope_{project_id}",
    ) or "Весь текущий отбор"
    if scope == "Весь текущий отбор":
        ids = dataframe["_analysis_id"].astype(str).tolist()
        render_badges([(f"выбрано · {len(ids):,}".replace(",", " "), "accent")])
        return ids

    visible = [
        column for column in ["_analysis_id", "Sample", "Grain", "Point", "Набор", "Минерал", "Generation", "PetroLab Generation"]
        if column in dataframe.columns
    ]
    source = dataframe[visible].head(3000).copy()
    source.insert(0, "Выбрать", False)
    if len(dataframe) > 3000:
        st.warning("Для ручного выбора показаны первые 3000 строк. Сузьте текущий поиск/фильтр, если нужны другие точки.")
    edited = st.data_editor(
        source,
        hide_index=True,
        width="stretch",
        height=360,
        disabled=[column for column in source.columns if column != "Выбрать"],
        column_config={"Выбрать": st.column_config.CheckboxColumn("✓")},
        key=f"batch_selection_{project_id}",
    )
    ids = edited.loc[edited["Выбрать"].fillna(False).astype(bool), "_analysis_id"].astype(str).tolist()
    render_badges([(f"выбрано · {len(ids):,}".replace(",", " "), "accent" if ids else "neutral")])
    return ids


def render_batch_actions(dataframe: pd.DataFrame, project_id: int) -> None:
    render_section_header("Массовые действия", "Отбор сначала, действие потом; каждое интерпретационное изменение записывается в журнал")
    st.caption(
        "Фильтр таблицы выше задаёт рабочий отбор. Можно применить действие ко всему отбору или отметить отдельные строки. "
        "Химия здесь не переписывается."
    )
    ids = _selection_editor(dataframe, int(project_id))
    if not ids:
        st.info("Выберите хотя бы одну точку.")
        return

    phase_tab, generation_tab, morphology_tab, context_tab = st.tabs([
        "Минерал / фаза", "Generation", "Морфология", "Sample / сессия",
    ])
    with phase_tab:
        st.caption(
            "Можно исправить уже разобранную точку. Она переедет в фазовый набор с тем же immutable analysis_id; "
            "фото, источник и физические связи сохранятся."
        )
        phase = st.text_input("Подтверждённая фаза", key=f"batch_phase_{project_id}", placeholder="например, calcic amphibole")
        confirm = st.checkbox(
            "Я проверил выбранные точки",
            key=f"batch_phase_confirm_{project_id}",
        )
        if st.button(
            "Назначить фазу выбранным",
            type="primary",
            disabled=not phase.strip() or not confirm,
            key=f"batch_phase_apply_{project_id}",
            width="stretch",
        ):
            try:
                count = reassign_phase_with_journal(int(project_id), ids, phase)
            except Exception as exc:
                st.error(f"Переклассификация остановлена: {exc}")
            else:
                st.success(f"Фаза изменена для {count} точек. Операцию можно отменить в «Истории действий».")
                st.session_state.pop(f"batch_selection_{project_id}", None)
                st.rerun()

    with generation_tab:
        generation = st.text_input("Generation", key=f"batch_generation_{project_id}", placeholder="например, N-X1")
        rationale = st.text_input("Почему · необязательно", key=f"batch_generation_reason_{project_id}")
        if st.button(
            "Назначить Generation",
            type="primary",
            disabled=not generation.strip(),
            key=f"batch_generation_apply_{project_id}",
            width="stretch",
        ):
            try:
                count = assign_generation_with_journal(int(project_id), ids, generation, rationale=rationale)
            except Exception as exc:
                st.error(f"Generation не сохранена: {exc}")
            else:
                st.success(f"Generation сохранена для {count} точек. Операцию можно отменить.")
                st.rerun()

    with morphology_tab:
        key = st.selectbox(
            "Что наблюдали",
            list(MORPHOLOGY_KEYS),
            format_func=lambda value: MORPHOLOGY_KEYS[value],
            key=f"batch_morph_key_{project_id}",
        )
        value = st.text_input("Значение", key=f"batch_morph_value_{project_id}", placeholder="ядро, кайма, включение…")
        if st.button(
            "Сохранить морфологию",
            type="primary",
            disabled=not value.strip(),
            key=f"batch_morph_apply_{project_id}",
            width="stretch",
        ):
            try:
                count = set_annotation_with_journal(
                    int(project_id), ids, namespace="morphology", key=str(key), value=value,
                    label=f"Морфология · {MORPHOLOGY_KEYS[str(key)]} → {value.strip()}",
                )
            except Exception as exc:
                st.error(f"Морфология не сохранена: {exc}")
            else:
                st.success(f"Морфология сохранена для {count} точек. Операцию можно отменить.")
                st.rerun()

    with context_tab:
        st.info(
            "Canonical Sample и Analytical Session задаются на уровне физического/методического контекста, а не произвольной колонки. "
            "PetroLab не будет молча перепривязывать отдельные точки к другому Sample."
        )
        if st.button("Открыть Sample и сессии", key=f"batch_sessions_{project_id}", width="stretch"):
            navigate("sessions")
            st.rerun()
