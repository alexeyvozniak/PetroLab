from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.db import list_accessible_datasets, load_dataset_dataframe
from petrolab.formula_workflow import recommended_method
from petrolab.phase_linkage import linked_phase_suggestions
from petrolab.phase_suggestions import (
    SUGGESTED_MINERAL_COLUMN,
    SUGGESTION_CONFIDENCE_COLUMN,
    SUGGESTION_REASON_COLUMN,
    attach_phase_suggestions,
    materialize_confirmed_phases,
    mineral_key_for_phase,
)
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project_id
from petrolab.workflow_screening import (
    OUTLIER_COLUMN,
    OUTLIER_REASON_COLUMN,
    attach_chemical_outlier_screen,
)

_MAJOR_PHASE_COLUMNS = {
    "SiO2", "TiO2", "Al2O3", "FeO", "FeOt", "Fe2O3", "MgO", "CaO", "Na2O", "K2O", "P2O5",
}
_LINKED_PHASE_COLUMN = "Фаза по физической связи"
_LINK_REASON_COLUMN = "Основание физической связи"
_LINK_CONFLICT_COLUMN = "Конфликт физической связи"


def _jump(route: str) -> None:
    navigate(route)
    st.rerun()


def _review_status(row: pd.Series) -> str:
    if bool(row.get(OUTLIER_COLUMN, False)):
        return "Выброс — проверить"
    confidence = str(row.get(SUGGESTION_CONFIDENCE_COLUMN, ""))
    reason = str(row.get(SUGGESTION_REASON_COLUMN, ""))
    if confidence == "high":
        return "Готово"
    if confidence == "medium":
        return "Вероятно"
    if "competing candidate" in reason:
        return "Вероятный микс / конкурирующие фазы"
    return "Не определено"


def _summary_table(review: pd.DataFrame) -> pd.DataFrame:
    table = review.copy()
    table["Фаза"] = table[SUGGESTED_MINERAL_COLUMN].fillna("").astype(str).str.strip().replace("", "Не определено / спорно")
    table["High"] = table[SUGGESTION_CONFIDENCE_COLUMN].eq("high").astype(int)
    table["Medium"] = table[SUGGESTION_CONFIDENCE_COLUMN].eq("medium").astype(int)
    table["Проверить"] = (~table[SUGGESTION_CONFIDENCE_COLUMN].isin(["high", "medium"])).astype(int)
    table["Выбросы"] = table[OUTLIER_COLUMN].fillna(False).astype(bool).astype(int)
    return (
        table.groupby("Фаза", dropna=False)
        .agg(Точек=("Фаза", "size"), High=("High", "sum"), Medium=("Medium", "sum"), Проверить=("Проверить", "sum"), Выбросы=("Выбросы", "sum"))
        .reset_index()
        .sort_values(["Точек", "Фаза"], ascending=[False, True])
    )


def _linked_summary_table(review: pd.DataFrame) -> pd.DataFrame:
    table = review.copy()
    label = table[_LINKED_PHASE_COLUMN].fillna("").astype(str).str.strip()
    conflict = table[_LINK_CONFLICT_COLUMN].fillna(False).astype(bool)
    table["Результат"] = label.where(label.ne(""), "Нет подтверждённой связанной фазы")
    table.loc[conflict, "Результат"] = "Конфликт связанных фаз"
    return (
        table.groupby("Результат", dropna=False)
        .size()
        .reset_index(name="Точек")
        .sort_values(["Точек", "Результат"], ascending=[False, True])
    )


def _recent_split_actions(project_id: int) -> None:
    recent = [int(value) for value in st.session_state.pop("workflow_recent_split_dataset_ids", [])]
    datasets = {int(item["id"]): item for item in list_accessible_datasets(project_id)}
    recent = [dataset_id for dataset_id in recent if dataset_id in datasets]
    if not recent:
        return
    st.session_state["workflow_focus_dataset_id"] = recent[0]
    st.success(f"Разбиение сохранено. Фазовых наборов в этом действии: {len(recent)}.")
    st.caption("Неразобранные, спорные и неподтверждённые точки остались в исходном наборе «Неразобранные / mixed».")
    choices = {int(dataset_id): datasets[int(dataset_id)] for dataset_id in recent}
    formula_candidates = [dataset_id for dataset_id, item in choices.items() if recommended_method(str(item["mineral_key"]))]
    c1, c2, c3, c4 = st.columns(4)
    if formula_candidates and c1.button("4 · Формулы", type="primary", width="stretch"):
        st.session_state["workflow_formula_dataset_id"] = formula_candidates[0]
        st.session_state.pop("formula_dataset", None)
        _jump("formulae")
    if c2.button("5 · Изображения", width="stretch"):
        st.session_state["workflow_image_dataset_id"] = recent[0]
        _jump("images")
    if c3.button("6 · Шлифы и точки", width="stretch"):
        _jump("slides")
    if c4.button("7 · Первый график", width="stretch"):
        st.session_state["workflow_plot_dataset_ids"] = recent
        st.session_state.pop("quick_plot_datasets", None)
        _jump("plots")
    if st.button("Продолжить в рабочем процессе", width="stretch"):
        _jump("workflow")


def _trace_only_hint(frame: pd.DataFrame) -> bool:
    measured = sorted(_MAJOR_PHASE_COLUMNS.intersection(frame.columns))
    trace_only = len(measured) < 3
    if not trace_only:
        return False
    st.warning(
        "В этом наборе мало major-element колонок для честного химического распознавания фазы. Это похоже на LA-ICP-MS / trace-only данные: минерал лучше наследовать через Sample, зерно, физическую точку/кратер или назначить вручную, а не угадывать по микроэлементам."
    )
    st.caption(
        "Для такого набора PetroLab не подготавливает ни одну химически угаданную фазу к автоматическому подтверждению. Если LA и EPMA явно связаны одной физической меткой, ниже появится фаза связанной зондовой точки."
    )
    c1, c2, c3 = st.columns(3)
    if c1.button("Sample и сессии", key="trace_to_sessions", width="stretch"):
        _jump("sessions")
    if c2.button("Точки и LA-кратеры", key="trace_to_measurements", width="stretch"):
        _jump("measurements")
    if c3.button("Шлиф / физическая точка", key="trace_to_slides", width="stretch"):
        _jump("slides")
    return True


def _attach_linked_phases(project_id: int, dataframe: pd.DataFrame) -> pd.DataFrame:
    out = dataframe.copy()
    ids = out["_analysis_id"].astype(str).tolist() if "_analysis_id" in out.columns else []
    linked = linked_phase_suggestions(project_id, ids)
    out[_LINKED_PHASE_COLUMN] = [linked.get(str(value)).phase_label if linked.get(str(value)) else "" for value in out.get("_analysis_id", pd.Series("", index=out.index))]
    out[_LINK_REASON_COLUMN] = [linked.get(str(value)).reason if linked.get(str(value)) else "" for value in out.get("_analysis_id", pd.Series("", index=out.index))]
    out[_LINK_CONFLICT_COLUMN] = [bool(linked.get(str(value)).conflict) if linked.get(str(value)) else False for value in out.get("_analysis_id", pd.Series("", index=out.index))]
    return out


def render_mixed_minerals_page() -> None:
    render_page_header(
        "Разбор фаз и выбросов",
        "PetroLab предлагает фазы, сразу показывает химически необычные точки и оставляет всё спорное в mixed до вашего решения.",
        eyebrow="Данные",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала выберите проект.")
        return
    project_id = int(project_id)
    _recent_split_actions(project_id)

    datasets = list_accessible_datasets(project_id)
    if not datasets:
        st.info("Сначала импортируйте сырой файл.")
        return
    by_id = {int(row["id"]): row for row in datasets}
    ids = list(by_id)
    requested = st.session_state.pop("workflow_mixed_dataset_id", None)
    default_id = int(requested) if requested is not None and int(requested) in by_id else ids[0]
    dataset_id = st.selectbox(
        "Набор для проверки",
        ids,
        index=ids.index(default_id),
        format_func=lambda value: f"{by_id[int(value)]['name']} · {by_id[int(value)]['mineral_key']} · {by_id[int(value)]['row_count']} точек",
        key="mixed_dataset",
    )
    dataset = by_id[int(dataset_id)]
    if str(dataset.get("mineral_key")) != "generic":
        st.info("Набор уже имеет минералогический модуль. Его можно проверить на выбросы и ошибочные фазы; разделяйте только те строки, которые действительно хотите переклассифицировать.")

    frame = load_dataset_dataframe(int(dataset_id), include_meta=True)
    if frame.empty:
        st.info("В наборе нет точек.")
        return

    trace_only = _trace_only_hint(frame)
    suggested = attach_phase_suggestions(frame)
    screened = attach_chemical_outlier_screen(suggested, group_column=SUGGESTED_MINERAL_COLUMN)
    screened["Статус разбора"] = screened.apply(_review_status, axis=1)
    if trace_only:
        screened = _attach_linked_phases(project_id, screened)
        linked_count = int(screened[_LINKED_PHASE_COLUMN].fillna("").astype(str).str.strip().ne("").sum())
        link_conflicts = int(screened[_LINK_CONFLICT_COLUMN].fillna(False).astype(bool).sum())
        screened["Статус разбора"] = "Нужна физическая привязка / ручное решение"
        screened.loc[screened[_LINKED_PHASE_COLUMN].astype(str).str.strip().ne(""), "Статус разбора"] = "Фаза найдена по физической связи"
        screened.loc[screened[_LINK_CONFLICT_COLUMN].fillna(False).astype(bool), "Статус разбора"] = "Конфликт связанных фаз"
    else:
        linked_count = 0
        link_conflicts = 0

    high = int((screened[SUGGESTION_CONFIDENCE_COLUMN] == "high").sum())
    medium = int((screened[SUGGESTION_CONFIDENCE_COLUMN] == "medium").sum())
    ambiguous = int((screened[SUGGESTION_CONFIDENCE_COLUMN] == "ambiguous").sum())
    unresolved = int((screened[SUGGESTION_CONFIDENCE_COLUMN] == "unresolved").sum())
    outliers = int(screened[OUTLIER_COLUMN].fillna(False).astype(bool).sum())
    if trace_only:
        render_badges([
            (f"{len(screened)} точек", "accent"),
            (f"{linked_count} фаз по физической связи", "success" if linked_count else "neutral"),
            (f"{link_conflicts} конфликтов связи", "warning" if link_conflicts else "neutral"),
            ("химическое автоназначение выключено", "warning"),
        ])
    else:
        render_badges([
            (f"{len(screened)} точек", "accent"),
            (f"{high} готово", "success"),
            (f"{medium} вероятно", "neutral"),
            (f"{ambiguous + unresolved} требуют решения", "warning"),
            (f"{outliers} потенциальных выбросов", "warning" if outliers else "neutral"),
        ])
        st.caption(
            "Выброс — только robust screening внутри предложенной фазы. Он никогда не удаляет и не исключает точку. "
            "Необычный природный состав может быть важнее статистического большинства."
        )

    render_section_header("Что нашлось", "Сводка перед ручной проверкой")
    st.dataframe(_linked_summary_table(screened) if trace_only else _summary_table(screened), width="stretch", hide_index=True)

    if trace_only:
        show_options = ["Все", "Есть физическая связь", "Требуют решения", "Конфликты связи"]
    else:
        show_options = ["Все", "Требуют решения", "Только выбросы", "High", "Medium"]
    show_mode = st.segmented_control(
        "Показать", show_options, default="Все", key=f"mixed_show_{dataset_id}"
    ) or "Все"
    view = screened
    if trace_only:
        if show_mode == "Есть физическая связь":
            view = view[view[_LINKED_PHASE_COLUMN].fillna("").astype(str).str.strip().ne("")]
        elif show_mode == "Требуют решения":
            view = view[view[_LINKED_PHASE_COLUMN].fillna("").astype(str).str.strip().eq("")]
        elif show_mode == "Конфликты связи":
            view = view[view[_LINK_CONFLICT_COLUMN].fillna(False).astype(bool)]
    else:
        if show_mode == "Требуют решения":
            view = view[~view[SUGGESTION_CONFIDENCE_COLUMN].isin(["high", "medium"]) | view[OUTLIER_COLUMN].fillna(False)]
        elif show_mode == "Только выбросы":
            view = view[view[OUTLIER_COLUMN].fillna(False)]
        elif show_mode == "High":
            view = view[view[SUGGESTION_CONFIDENCE_COLUMN] == "high"]
        elif show_mode == "Medium":
            view = view[view[SUGGESTION_CONFIDENCE_COLUMN] == "medium"]

    if not trace_only:
        phase_options = sorted(value for value in screened[SUGGESTED_MINERAL_COLUMN].dropna().astype(str).unique() if value.strip())
        chosen_phase = st.selectbox("Фаза", ["Все", *phase_options], key=f"mixed_phase_filter_{dataset_id}")
        if chosen_phase != "Все":
            view = view[view[SUGGESTED_MINERAL_COLUMN].astype(str) == chosen_phase]
    else:
        chosen_phase = "Все"

    policy_options = ["Только high без выбросов", "High + medium без выбросов", "Ничего — выбрать вручную"]
    policy = st.radio(
        "Что подготовить к подтверждению",
        policy_options,
        index=2 if trace_only else 0,
        horizontal=True,
        key=f"mixed_policy_{dataset_id}",
        disabled=trace_only,
        help=(
            "Для trace-only LA автоматическое подтверждение отключено: физическая связь только подставляет фазу в поле, а галочку ставите вы."
            if trace_only else
            "Это только начальные галочки. Любую строку можно включить, выключить или переименовать вручную."
        ),
    )

    display_cols = [
        column for column in [
            "_analysis_id", "Sample", "Grain", "Point", "SiO2", "TiO2", "Al2O3", "FeO", "FeOt",
            "MgO", "CaO", "Na2O", "K2O", "P2O5", "Nb2O5", "ZrO2",
            _LINKED_PHASE_COLUMN, _LINK_REASON_COLUMN, _LINK_CONFLICT_COLUMN,
            SUGGESTED_MINERAL_COLUMN, SUGGESTION_CONFIDENCE_COLUMN, "Статус разбора",
            OUTLIER_COLUMN, OUTLIER_REASON_COLUMN, SUGGESTION_REASON_COLUMN,
        ] if column in view.columns
    ]
    review = view[display_cols].copy()
    review["Подтвердить"] = False
    if trace_only:
        review["Подтверждённая фаза"] = review[_LINKED_PHASE_COLUMN].fillna("").astype(str)
    else:
        review["Подтверждённая фаза"] = review[SUGGESTED_MINERAL_COLUMN].fillna("").astype(str)
    no_outlier = ~review.get(OUTLIER_COLUMN, pd.Series(False, index=review.index)).fillna(False).astype(bool)
    if not trace_only and policy == "Только high без выбросов":
        review["Подтвердить"] = review[SUGGESTION_CONFIDENCE_COLUMN].eq("high") & no_outlier
    elif not trace_only and policy == "High + medium без выбросов":
        review["Подтвердить"] = review[SUGGESTION_CONFIDENCE_COLUMN].isin(["high", "medium"]) & no_outlier

    render_section_header("Проверка", f"Показано {len(review)} из {len(screened)} точек")
    st.caption(
        "«Подтверждённая фаза» — свободное поле: можно принять предложение, принять фазу по физической связи, написать своё название или оставить пустым. "
        "PetroLab сам выберет безопасный расчётный модуль; если подходящего модуля нет, фаза сохранится как отдельный generic-набор."
    )
    editor_key = f"mixed_review_{dataset_id}_{show_mode}_{chosen_phase}_{policy}"
    edited = st.data_editor(
        review,
        width="stretch",
        hide_index=True,
        height=650,
        disabled=[column for column in review.columns if column not in {"Подтвердить", "Подтверждённая фаза"}],
        column_config={
            "Подтвердить": st.column_config.CheckboxColumn("В минерал", help="Только отмеченные строки будут перемещены."),
            "Подтверждённая фаза": st.column_config.TextColumn("Подтверждённая фаза", help="Можно ввести собственное название."),
            SUGGESTED_MINERAL_COLUMN: st.column_config.TextColumn("Химическое предложение"),
            SUGGESTION_CONFIDENCE_COLUMN: st.column_config.TextColumn("Уверенность химии"),
            _LINKED_PHASE_COLUMN: st.column_config.TextColumn("Фаза по связи"),
            _LINK_REASON_COLUMN: st.column_config.TextColumn("Почему связь"),
            _LINK_CONFLICT_COLUMN: st.column_config.CheckboxColumn("Конфликт связи"),
            OUTLIER_COLUMN: st.column_config.CheckboxColumn("Выброс?"),
            OUTLIER_REASON_COLUMN: st.column_config.TextColumn("Почему выброс"),
            SUGGESTION_REASON_COLUMN: st.column_config.TextColumn("Почему химическая фаза"),
        },
        key=editor_key,
    )

    assignments = {
        str(row["_analysis_id"]): str(row["Подтверждённая фаза"]).strip()
        for _, row in edited.iterrows()
        if bool(row.get("Подтвердить")) and str(row.get("Подтверждённая фаза", "")).strip()
    }
    selected_phases = sorted(set(assignments.values()), key=str.casefold)
    if selected_phases:
        st.caption(
            "Будут использованы: " + "; ".join(
                f"{phase} → модуль {mineral_key_for_phase(phase)}" for phase in selected_phases
            )
        )
    st.caption(
        f"К разбиению выбрано {len(assignments)} из {len(review)} показанных строк. "
        "Все остальные останутся в «Неразобранные / mixed» и их можно разобрать позже."
    )

    confirm = st.checkbox(
        "Я проверил выбранные строки и хочу переместить только их в фазовые наборы",
        key=f"mixed_confirm_{dataset_id}_{show_mode}_{chosen_phase}_{policy}",
    )
    if st.button(
        "Применить разбиение",
        type="primary",
        disabled=not assignments or not confirm,
        key=f"mixed_materialize_{dataset_id}_{show_mode}_{chosen_phase}_{policy}",
        width="stretch",
    ):
        try:
            created = materialize_confirmed_phases(int(dataset_id), assignments)
        except Exception as exc:
            st.error(f"Разбиение остановлено: {exc}")
        else:
            recent = list(dict.fromkeys(int(value) for value in created.values()))
            st.session_state["workflow_recent_split_dataset_ids"] = recent
            if recent:
                st.session_state["workflow_focus_dataset_id"] = recent[0]
            st.session_state["workflow_recent_mixed_dataset_id"] = int(dataset_id)
            st.success("Разбиение завершено без дублирования analysis_id. Неразобранные точки сохранены отдельно.")
            st.rerun()
