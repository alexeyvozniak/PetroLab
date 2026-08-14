from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, list_work_groups, work_group_map
from petrolab.generations import (
    PETROLAB_GENERATION_COLUMN,
    SOURCE_GENERATION_COLUMN,
    assign_generation,
    clear_generation,
    generation_history,
    generation_map,
    promote_work_group,
)
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project_id
from petrolab.db import connect


def _project_analysis_ids(project_id: int) -> set[str]:
    with connect() as con:
        rows = con.execute(
            """SELECT a.analysis_id FROM analysis_rows a
               JOIN datasets d ON d.id=a.dataset_id
               WHERE d.project_id=?""",
            (int(project_id),),
        ).fetchall()
    return {str(row["analysis_id"]) for row in rows}


def render_generations_page() -> None:
    render_page_header(
        "Поколения",
        "Превращайте рабочие группы в проверяемые интерпретации, не меняя исходную Generation из Excel или статьи.",
        eyebrow="Интерпретация",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала выберите проект.")
        return
    project_id = int(project_id)
    allowed_ids = _project_analysis_ids(project_id)
    assignments = {aid: name for aid, name in generation_map().items() if aid in allowed_ids}
    groups = list_work_groups()
    render_badges([
        (f"{len(assignments)} размечено", "accent"),
        (f"{len(set(assignments.values()))} поколений", "neutral"),
        (f"{len(groups)} рабочих групп", "neutral"),
    ])
    st.info(
        f"Исходная колонка хранится как **{SOURCE_GENERATION_COLUMN}**. "
        f"Ваша интерпретация доступна во всех Analysis Scope как **{PETROLAB_GENERATION_COLUMN}**."
    )

    left, right = st.columns(2)
    with left:
        st.subheader("Утвердить рабочую группу")
        if not groups:
            st.caption("Рабочих групп пока нет. Их можно создавать выделением точек на XY-графиках или из статистических кластеров.")
        else:
            group_name = st.selectbox("Рабочая группа", groups, key="generation_work_group")
            generation_name = st.text_input("Название Generation", value=group_name, key="generation_name_from_group")
            rationale = st.text_area("Почему вы считаете это отдельным поколением · необязательно", height=80, key="generation_rationale")
            if st.button("Утвердить как Generation", type="primary", disabled=not generation_name.strip(), key="promote_generation"):
                changed = promote_work_group(group_name, generation_name, rationale=rationale)
                st.success(f"Generation сохранена для {changed} анализов. Исходные данные не изменены.")
                st.rerun()

    with right:
        st.subheader("Назначить / исправить вручную")
        work_groups = work_group_map()
        candidate_ids = sorted(aid for aid in work_groups if aid in allowed_ids)
        if candidate_ids:
            labels = {f"{work_groups[aid]} · {aid[:10]}": aid for aid in candidate_ids}
            selected = st.multiselect("Анализы из рабочих групп", list(labels), key="generation_manual_ids")
            manual_name = st.text_input("Новая PetroLab Generation", key="generation_manual_name")
            manual_reason = st.text_input("Комментарий", key="generation_manual_reason")
            c1, c2 = st.columns(2)
            if c1.button("Назначить", disabled=not selected or not manual_name.strip(), key="generation_manual_assign"):
                changed = assign_generation([labels[label] for label in selected], manual_name, rationale=manual_reason)
                st.success(f"Обновлено: {changed}.")
                st.rerun()
            if c2.button("Снять интерпретацию", disabled=not selected, key="generation_manual_clear"):
                changed = clear_generation([labels[label] for label in selected], rationale=manual_reason)
                st.success(f"Снято назначений: {changed}.")
                st.rerun()
        else:
            st.caption("После создания рабочих групп здесь появятся точки для ручной корректировки.")

    st.subheader("Текущая разметка")
    if assignments:
        counts = pd.Series(assignments).value_counts().rename_axis(PETROLAB_GENERATION_COLUMN).reset_index(name="Анализов")
        st.dataframe(counts, width="stretch", hide_index=True)
    else:
        st.caption("PetroLab Generation пока не назначены.")

    with st.expander("История решений", expanded=False):
        history = [row for row in generation_history() if str(row["analysis_id"]) in allowed_ids]
        if history:
            view = pd.DataFrame(history)
            view = view.rename(columns={
                "analysis_id": "analysis_id",
                "previous_generation": "Было",
                "new_generation": "Стало",
                "rationale": "Комментарий",
                "source_kind": "Источник решения",
                "source_value": "Рабочая группа",
                "changed_at": "Когда",
            })
            st.dataframe(view, width="stretch", hide_index=True, height=340)
        else:
            st.caption("История пока пуста.")
