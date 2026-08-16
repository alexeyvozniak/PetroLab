from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, clear_work_group, list_work_groups, set_work_group
from petrolab.dataframe_utils import human_point_label
from petrolab.generations import PETROLAB_GENERATION_COLUMN, assign_generation
from petrolab.ui.navigation import navigate
from petrolab.ui.selection_context import (
    clear_selection,
    read_row_states,
    read_selection,
    set_row_state,
)


_CHEMISTRY_PRIORITY = (
    "SiO2", "TiO2", "Al2O3", "Cr2O3", "FeOt", "FeO", "Fe2O3t",
    "MnO", "MgO", "CaO", "Na2O", "K2O", "P2O5", "F", "Cl",
    "Mg#", "Ni", "Cr", "Co", "Sc", "V", "Rb", "Sr", "Ba", "Nb", "Ta", "Zr", "Hf",
)


def render_selection_mode(*, key_prefix: str, default: str = "replace") -> str:
    labels = {
        "Заменить": "replace",
        "Добавить": "add",
        "Вычесть": "subtract",
    }
    reverse = {value: label for label, value in labels.items()}
    current = reverse.get(default, "Заменить")
    choice = st.segmented_control(
        "Как менять отбор",
        list(labels),
        default=current,
        key=f"{key_prefix}_selection_mode",
        help="Заменить — новый отбор вместо старого; Добавить — расширить; Вычесть — убрать выбранные точки.",
    )
    return labels.get(str(choice or current), "replace")


def selected_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    context = read_selection()
    if dataframe.empty or not context.analysis_ids or "_analysis_id" not in dataframe.columns:
        return dataframe.iloc[0:0].copy()
    wanted = set(context.analysis_ids)
    return dataframe[dataframe["_analysis_id"].astype(str).isin(wanted)].copy()


def _summary_columns(dataframe: pd.DataFrame) -> list[str]:
    identity = [
        column for column in (
            "Sample", "Grain", "Point", PETROLAB_GENERATION_COLUMN, "Generation", WORK_GROUP_COLUMN,
            "Textural zone", "Источник", "Набор", "Минерал",
        )
        if column in dataframe.columns
    ]
    chemistry = [column for column in _CHEMISTRY_PRIORITY if column in dataframe.columns]
    return [*identity, *chemistry[:14]]


def _selected_dataset_ids(selected: pd.DataFrame) -> list[int]:
    if selected.empty or "_dataset_id" not in selected.columns:
        return []
    numeric = pd.to_numeric(selected["_dataset_id"], errors="coerce").dropna()
    return list(dict.fromkeys(int(value) for value in numeric.tolist()))


def render_selection_panel(
    dataframe: pd.DataFrame,
    *,
    project_id: int | None,
    key_prefix: str,
    expanded: bool = True,
) -> None:
    context = read_selection()
    if not context.analysis_ids:
        st.caption("Нет активного отбора. Выберите строки таблицы или точки на графике.")
        return

    selected = selected_dataframe(dataframe)
    dataset_ids = _selected_dataset_ids(selected)
    title = f"Выбрано: {context.count}"
    if context.label:
        title += f" · {context.label}"
    with st.container(border=True):
        header, clear_col = st.columns([5, 1])
        header.markdown(f"**{title}**")
        header.caption(f"Источник отбора: {context.origin or 'текущий вид'}")
        if clear_col.button("Очистить", key=f"{key_prefix}_clear_selection", width="stretch"):
            clear_selection()
            st.rerun()

        if not selected.empty:
            view = selected.copy()
            view.insert(0, "Точка", [human_point_label(row) for _, row in view.iterrows()])
            columns = ["Точка", *_summary_columns(view)]
            columns = list(dict.fromkeys(column for column in columns if column in view.columns))
            st.dataframe(view[columns].head(500), width="stretch", hide_index=True, height=220)
        else:
            st.info("Отбор сохранён, но выбранные анализы не входят в текущий вид. Перейдите к таблице/графику с этим контекстом.")

        st.caption("Один и тот же отбор используется между таблицей, XY, multi-panel и статистикой. Сохранение как группа/Generation — отдельное действие.")
        a1, a2, a3, a4, a5 = st.columns(5)
        if a1.button("XY", key=f"{key_prefix}_to_xy", width="stretch"):
            if dataset_ids:
                st.session_state["workflow_plot_dataset_ids"] = dataset_ids
            # Selection remains a highlight, not a filter: the XY view keeps the
            # full dataset population and reads the same canonical analysis_ids.
            navigate("plots")
            st.rerun()
        if a2.button("Несколько", key=f"{key_prefix}_to_multi", width="stretch"):
            if dataset_ids:
                st.session_state["workflow_plot_dataset_ids"] = dataset_ids
            navigate("multi_panel")
            st.rerun()
        if a3.button("Статистика", key=f"{key_prefix}_to_stats", width="stretch"):
            st.session_state["statistics_dataset_ids_pending"] = dataset_ids
            navigate("statistics")
            st.rerun()
        if a4.button("Профиль", key=f"{key_prefix}_to_profile", width="stretch"):
            st.session_state["grain_profile_dataset_ids"] = dataset_ids
            st.session_state["grain_profile_analysis_ids"] = list(context.analysis_ids)
            st.session_state["grain_profile_context"] = {"project_id": project_id} if project_id is not None else {}
            navigate("grain_profile")
            st.rerun()
        if a5.button("Формула / APFU", key=f"{key_prefix}_to_formula", width="stretch"):
            st.session_state["formulae_dataset_ids_pending"] = dataset_ids
            st.session_state["formulae_analysis_ids_pending"] = list(context.analysis_ids)
            navigate("formulae")
            st.rerun()

        with st.expander("Сохранить / классифицировать отбор", expanded=False):
            existing = list_work_groups(project_id) if project_id is not None else list_work_groups()
            choice = st.selectbox(
                "Рабочая группа",
                ["Новая группа…", *existing],
                key=f"{key_prefix}_group_choice",
            )
            group_name = ""
            if choice == "Новая группа…":
                group_name = st.text_input(
                    "Название новой рабочей группы",
                    key=f"{key_prefix}_group_name",
                    placeholder="например, предполагаемые ксенокристы",
                ).strip()
            else:
                group_name = str(choice).strip()
            g1, g2 = st.columns(2)
            if g1.button(
                "Назначить рабочую группу",
                disabled=not group_name,
                key=f"{key_prefix}_assign_group",
                width="stretch",
            ):
                changed = set_work_group(context.analysis_ids, group_name)
                st.success(f"Рабочая группа назначена для {changed} анализов.")
                st.rerun()
            if g2.button("Убрать рабочую группу", key=f"{key_prefix}_clear_group", width="stretch"):
                changed = clear_work_group(context.analysis_ids)
                st.success(f"Рабочая группа снята у {changed} анализов.")
                st.rerun()

            generation = st.text_input(
                "Утвердить как PetroLab Generation",
                key=f"{key_prefix}_generation_name",
                placeholder="название поколения",
            ).strip()
            rationale = st.text_input(
                "Комментарий к интерпретации · необязательно",
                key=f"{key_prefix}_generation_reason",
            )
            if st.button(
                "Утвердить Generation",
                disabled=not generation,
                key=f"{key_prefix}_assign_generation",
                width="stretch",
            ):
                changed = assign_generation(context.analysis_ids, generation, rationale=rationale)
                st.success(f"Generation сохранена для {changed} анализов; исходная колонка не изменена.")
                st.rerun()

        with st.expander("Видимость и статистика", expanded=False):
            states = read_row_states()
            current = set(context.analysis_ids)
            h1, h2 = st.columns(2)
            if h1.button("Скрыть на графиках", key=f"{key_prefix}_hide", width="stretch"):
                set_row_state("hidden", context.analysis_ids, mode="add")
                st.rerun()
            if h2.button("Вернуть скрытые", key=f"{key_prefix}_unhide", width="stretch"):
                set_row_state("hidden", context.analysis_ids, mode="subtract")
                st.rerun()
            e1, e2 = st.columns(2)
            if e1.button("Исключить из статистики", key=f"{key_prefix}_exclude", width="stretch"):
                set_row_state("excluded", context.analysis_ids, mode="add")
                st.rerun()
            if e2.button("Вернуть в статистику", key=f"{key_prefix}_include", width="stretch"):
                set_row_state("excluded", context.analysis_ids, mode="subtract")
                st.rerun()
            hidden_here = len(current & set(states.hidden))
            excluded_here = len(current & set(states.excluded))
            st.caption(
                f"В текущем отборе: скрыто {hidden_here}; исключено из статистики {excluded_here}. "
                "Hide и Exclude не меняют Selection, Work Group или Generation."
            )
