from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, work_group_map
from petrolab.generations import (
    PETROLAB_GENERATION_COLUMN,
    SOURCE_GENERATION_COLUMN,
    assign_generation,
    clear_generation,
    generation_history,
    generation_map,
)
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project_id
from petrolab.db import connect, list_accessible_datasets


def _project_analysis_ids(project_id: int) -> set[str]:
    """Return analysis ids visible in the project, including shared-library datasets.

    Dataset ownership is not project membership in PetroLab: one immutable dataset
    may live in the hidden library and be linked to several projects.  Generation
    decisions therefore have to follow the same accessible-dataset contract as
    the rest of the UI.
    """
    dataset_ids = [int(item["id"]) for item in list_accessible_datasets(int(project_id))]
    if not dataset_ids:
        return set()
    allowed: set[str] = set()
    with connect() as con:
        for start in range(0, len(dataset_ids), 800):
            chunk = dataset_ids[start : start + 800]
            rows = con.execute(
                "SELECT analysis_id FROM analysis_rows WHERE dataset_id IN ("
                + ",".join("?" for _ in chunk)
                + ")",
                chunk,
            ).fetchall()
            allowed.update(str(row["analysis_id"]) for row in rows)
    return allowed


def _project_work_group_map(allowed_ids: set[str]) -> dict[str, str]:
    mapping = work_group_map()
    return {analysis_id: group for analysis_id, group in mapping.items() if analysis_id in allowed_ids}


def _project_work_groups(allowed_ids: set[str]) -> list[str]:
    return sorted(set(_project_work_group_map(allowed_ids).values()), key=str.casefold)


def _promote_project_work_group(
    allowed_ids: set[str],
    work_group: str,
    generation_name: str,
    *,
    rationale: str = "",
) -> int:
    """Promote only the active project's members of a globally named work group."""
    name = str(work_group).strip()
    if not name:
        raise ValueError("Укажите рабочую группу")
    mapping = _project_work_group_map(allowed_ids)
    ids = [analysis_id for analysis_id, group in mapping.items() if group == name]
    if not ids:
        raise ValueError("В этой рабочей группе нет анализов активного проекта")
    return assign_generation(
        ids,
        generation_name,
        rationale=rationale,
        source_kind="work_group",
        source_value=name,
    )


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
    work_groups = _project_work_group_map(allowed_ids)
    groups = sorted(set(work_groups.values()), key=str.casefold)
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
            project_group_size = sum(1 for group in work_groups.values() if group == group_name)
            st.caption(f"Будут изменены только {project_group_size} анализов этой группы, доступных в активном проекте.")
            if st.button("Утвердить как Generation", type="primary", disabled=not generation_name.strip(), key="promote_generation"):
                changed = _promote_project_work_group(
                    allowed_ids,
                    group_name,
                    generation_name,
                    rationale=rationale,
                )
                st.success(f"Generation сохранена для {changed} анализов активного проекта. Исходные данные не изменены.")
                st.rerun()

    with right:
        st.subheader("Назначить / исправить вручную")
        candidate_ids = sorted(work_groups)
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
        history = generation_history(allowed_ids)
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