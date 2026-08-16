from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, work_group_map
from petrolab.dataframe_utils import human_point_label
from petrolab.db import connect, list_accessible_datasets
from petrolab.derived import load_unified_with_derived
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


_CHEMISTRY = ("SiO2", "TiO2", "Al2O3", "Cr2O3", "FeOt", "FeO", "MgO", "CaO", "Na2O", "K2O", "Mg#")


def _project_analysis_ids(project_id: int) -> set[str]:
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


def _promote_project_work_group(
    allowed_ids: set[str],
    work_group: str,
    generation_name: str,
    *,
    rationale: str = "",
) -> int:
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


def _project_dataframe(project_id: int) -> pd.DataFrame:
    dataset_ids = [int(item["id"]) for item in list_accessible_datasets(project_id)]
    if not dataset_ids:
        return pd.DataFrame()
    return load_unified_with_derived(project_id, dataset_ids)


def _manual_table(dataframe: pd.DataFrame, work_groups: dict[str, str]) -> tuple[pd.DataFrame, dict[int, str]]:
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        return pd.DataFrame(), {}
    work = dataframe[dataframe["_analysis_id"].astype(str).isin(set(work_groups))].copy()
    if work.empty:
        return pd.DataFrame(), {}
    work[WORK_GROUP_COLUMN] = [work_groups.get(str(value), "") for value in work["_analysis_id"]]
    rows = pd.DataFrame({
        "Выбрать": False,
        "Точка": [human_point_label(row) for _, row in work.iterrows()],
        WORK_GROUP_COLUMN: work[WORK_GROUP_COLUMN].astype(str).tolist(),
    })
    for column in ["Sample", "Grain", "Point", PETROLAB_GENERATION_COLUMN, SOURCE_GENERATION_COLUMN, "Generation", *_CHEMISTRY]:
        if column in work.columns and column not in rows.columns:
            rows[column] = work[column].to_numpy()
    mapping = {index: str(value) for index, value in enumerate(work["_analysis_id"].astype(str).tolist())}
    return rows, mapping


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
    dataframe = _project_dataframe(project_id)
    point_labels = {
        str(row["_analysis_id"]): human_point_label(row)
        for _, row in dataframe.iterrows()
        if "_analysis_id" in dataframe.columns
    }

    render_badges([
        (f"{len(assignments)} размечено", "accent"),
        (f"{len(set(assignments.values()))} поколений", "neutral"),
        (f"{len(groups)} рабочих групп", "neutral"),
    ])
    st.info(
        f"Исходная колонка хранится как **{SOURCE_GENERATION_COLUMN}**. "
        f"Ваша интерпретация доступна во всех представлениях как **{PETROLAB_GENERATION_COLUMN}**."
    )

    left, right = st.columns(2)
    with left:
        st.subheader("Утвердить рабочую группу")
        if not groups:
            st.caption("Рабочих групп пока нет. Их можно создавать из общего отбора в таблице, XY или статистике.")
        else:
            group_name = st.selectbox("Рабочая группа", groups, key="generation_work_group")
            generation_name = st.text_input("Название Generation", value=group_name, key="generation_name_from_group")
            rationale = st.text_area("Почему вы считаете это отдельным поколением · необязательно", height=80, key="generation_rationale")
            project_group_size = sum(1 for group in work_groups.values() if group == group_name)
            st.caption(f"Будут изменены только {project_group_size} анализов этой группы в активном проекте.")
            if st.button("Утвердить как Generation", type="primary", disabled=not generation_name.strip(), key="promote_generation"):
                changed = _promote_project_work_group(allowed_ids, group_name, generation_name, rationale=rationale)
                st.success(f"Generation сохранена для {changed} анализов. Исходные данные не изменены.")
                st.rerun()

    with right:
        st.subheader("Назначить / исправить вручную")
        table, index_to_id = _manual_table(dataframe, work_groups)
        if table.empty:
            st.caption("После создания рабочих групп здесь появятся точки для ручной корректировки.")
        else:
            edited = st.data_editor(
                table,
                width="stretch",
                hide_index=True,
                height=330,
                disabled=[column for column in table.columns if column != "Выбрать"],
                column_config={"Выбрать": st.column_config.CheckboxColumn("✓", width="small")},
                key="generation_manual_table",
            )
            selected_rows = edited.index[edited["Выбрать"].fillna(False).astype(bool)].tolist()
            selected_ids = [index_to_id[int(index)] for index in selected_rows if int(index) in index_to_id]
            manual_name = st.text_input("Новая PetroLab Generation", key="generation_manual_name")
            manual_reason = st.text_input("Комментарий", key="generation_manual_reason")
            c1, c2 = st.columns(2)
            if c1.button("Назначить", disabled=not selected_ids or not manual_name.strip(), key="generation_manual_assign"):
                changed = assign_generation(selected_ids, manual_name, rationale=manual_reason)
                st.success(f"Обновлено: {changed}.")
                st.rerun()
            if c2.button("Снять интерпретацию", disabled=not selected_ids, key="generation_manual_clear"):
                changed = clear_generation(selected_ids, rationale=manual_reason)
                st.success(f"Снято назначений: {changed}.")
                st.rerun()

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
            if "analysis_id" in view.columns:
                view.insert(0, "Точка", [point_labels.get(str(value), "Точка из прежней версии") for value in view["analysis_id"]])
                view = view.drop(columns=["analysis_id"])
            view = view.rename(columns={
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
