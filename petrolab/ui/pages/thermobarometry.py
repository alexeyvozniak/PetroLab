from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from petrolab.advisory_policy import ADVISORY_POLICY_ID
from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.thermobarometry import (
    PUTIRKA_2008_CPX_T32D,
    QC_FAIL,
    QC_INSUFFICIENT_INPUT,
    QC_NOT_APPLICABLE,
    QC_PASS,
    QC_WARNING,
    calculate_putirka_2008_cpx_only_t32d,
    list_runs,
    save_run,
)
from petrolab.ui.layout import render_badges, render_hint, render_page_header, render_section_header
from petrolab.ui.project_context import active_project_id


_CPX_KEY = "clinopyroxene"
_IDENTITY_COLUMNS = ("Sample", "Grain", "Point", "Generation", "Набор", "_analysis_id")


def _candidate_datasets(project_id: int) -> list[dict]:
    return [
        dataset for dataset in list_accessible_datasets(project_id)
        if str(dataset.get("mineral_key", "")) == _CPX_KEY
    ]


def _identity_preview(dataframe: pd.DataFrame) -> list[str]:
    return [column for column in _IDENTITY_COLUMNS if column in dataframe.columns]


def _run_history(project_id: int) -> None:
    runs = list_runs(project_id)
    if not runs:
        return
    with st.expander("Сохранённые расчёты", expanded=False):
        rows = []
        for run in runs[:50]:
            passed = sum(1 for row in run.results if row.get("Thermobarometry status") == QC_PASS)
            rows.append({
                "Run": run.id,
                "Метод": run.method_title,
                "Точек": len(run.input_analysis_ids),
                "PASS": passed,
                "Статус источников": "Актуален" if run.is_current else "Требует пересчёта",
                "Время": run.calculated_at,
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.caption(
            "Результаты привязаны к точным _analysis_id и отпечаткам исходной химии. "
            "После правки входных данных старый run не удаляется, но помечается как требующий пересчёта."
        )


def render_thermobarometry_page() -> None:
    render_page_header(
        "Термобарометрия",
        "Отдельный научный журнал расчётов: выбранные точки, допущения, QC и результаты хранятся вместе — исходная химия не меняется.",
        eyebrow="Исследование",
        context="Первый узкий workflow: клинопироксен → заданное давление → температура",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала создайте или выберите проект.")
        return

    datasets = _candidate_datasets(project_id)
    if not datasets:
        st.info(
            "В активном проекте пока нет наборов с минералом «Клинопироксен». "
            "Импортируйте их через «Новые анализы» и назначьте фазу — тогда они появятся здесь."
        )
        _run_history(project_id)
        return

    render_badges([
        ("Cpx-only", "accent"),
        ("Eq. 32d", "neutral"),
        ("P — явное допущение", "warning"),
        ("Исходная химия не изменяется", "success"),
    ])
    render_hint("Начните с одного набора и разумной группы точек. Парные mineral–melt и ML-модели будут отдельными workflow, а не настройками этой формы.")

    labels = {dataset_label(dataset): int(dataset["id"]) for dataset in datasets}
    selected_labels = st.multiselect(
        "Наборы Cpx", list(labels), default=list(labels), key="thermobarometry_datasets"
    )
    if not selected_labels:
        st.info("Выберите хотя бы один набор Cpx.")
        return
    selected_ids = [labels[label] for label in selected_labels]
    source = load_unified_with_derived(project_id, selected_ids)
    if "Минерал" in source.columns:
        source = source[source["Минерал"].astype(str) == _CPX_KEY].copy()
    if source.empty:
        st.warning("В выбранных наборах нет строк Cpx.")
        return
    if "_analysis_id" not in source.columns:
        st.error("У выбранных строк нет стабильных идентификаторов; расчёт небезопасен.")
        return
    source = source.drop_duplicates("_analysis_id").reset_index(drop=True)

    render_section_header("1. Выберите точки", "Сначала проверьте, что это именно Cpx одной осмысленной текстурной популяции")
    query = st.text_input("Фильтр по Sample / Grain / Point / Generation", key="thermobarometry_search")
    filtered = source.copy()
    if query.strip():
        needle = query.strip().casefold()
        mask = pd.Series(False, index=filtered.index)
        for column in _identity_preview(filtered):
            mask |= filtered[column].astype(str).str.casefold().str.contains(needle, na=False)
        filtered = filtered.loc[mask].copy()
    if filtered.empty:
        st.warning("После фильтрации не осталось точек.")
        return

    choice = st.radio(
        "Что рассчитать", ["Все отфильтрованные точки", "Отобрать вручную"], horizontal=True,
        key="thermobarometry_selection_mode",
    )
    selection = filtered
    preview_columns = _identity_preview(filtered) + [
        column for column in PUTIRKA_2008_CPX_T32D.required_components if column in filtered.columns
    ]
    if choice == "Отобрать вручную":
        editor = filtered[preview_columns].copy()
        editor.insert(0, "Рассчитать", False)
        edited = st.data_editor(
            editor, width="stretch", hide_index=True, key="thermobarometry_selector",
            column_config={"Рассчитать": st.column_config.CheckboxColumn("Рассчитать")},
            disabled=[column for column in editor.columns if column != "Рассчитать"],
        )
        chosen_ids = edited.loc[edited["Рассчитать"], "_analysis_id"].astype(str).tolist()
        selection = filtered[filtered["_analysis_id"].astype(str).isin(chosen_ids)].copy()
    else:
        st.dataframe(filtered[preview_columns].head(500), width="stretch", hide_index=True, height=260)
        if len(filtered) > 500:
            st.caption(f"В preview показано 500 из {len(filtered)} точек; расчёт будет применён ко всем отфильтрованным.")
    if selection.empty:
        st.info("Отметьте хотя бы одну точку.")
        return

    render_section_header("2. Укажите допущение", "Eq. 32d возвращает температуру только при независимо заданном давлении")
    pressure = st.number_input("Давление, kbar", min_value=0.0, value=2.0, step=0.1, key="thermobarometry_pressure")
    confirmed = st.checkbox(
        "Подтверждаю: это магматический Cpx, применение anhydrous Eq. 32d оправдано, а давление выбрано осмысленно.",
        key="thermobarometry_applicability",
    )
    with st.expander("Метод, ограничения и источник", expanded=False):
        st.write(f"**Калибровка:** {PUTIRKA_2008_CPX_T32D.title}")
        st.write(f"**Источник:** {PUTIRKA_2008_CPX_T32D.source_citation} DOI: {PUTIRKA_2008_CPX_T32D.source_doi}")
        st.write(f"**Входы:** {', '.join(PUTIRKA_2008_CPX_T32D.required_components)}")
        st.write(f"**Область:** {PUTIRKA_2008_CPX_T32D.calibration_range}")
        st.write(f"**Ошибка:** {PUTIRKA_2008_CPX_T32D.uncertainty}")
        st.warning("Не используйте этот режим для водсодержащего Cpx, пар mineral–melt или как независимый барометр.")

    result = calculate_putirka_2008_cpx_only_t32d(
        selection, pressure_kbar=float(pressure), applicability_confirmed=bool(confirmed)
    )
    display = pd.concat([selection[_identity_preview(selection)].reset_index(drop=True), result.reset_index(drop=True)], axis=1)
    counts = result["Thermobarometry status"].value_counts()
    render_section_header("3. Предпросмотр и QC", "PASS попадает в научный итог; FAIL и неполные строки остаются видимыми для диагностики")
    render_badges([
        (f"{len(selection)} выбрано", "neutral"),
        (f"{int(counts.get(QC_PASS, 0))} подтверждённых", "success"),
        (f"{int(counts.get(QC_WARNING, 0))} с предупреждением", "warning"),
        (f"{int(counts.get(QC_FAIL, 0))} FAIL", "warning"),
        (f"{int(counts.get(QC_INSUFFICIENT_INPUT, 0))} неполных", "warning"),
        (f"{int(counts.get(QC_NOT_APPLICABLE, 0))} требуют подтверждения", "danger"),
    ])
    st.dataframe(display.head(1000), width="stretch", hide_index=True, height=360)

    if not confirmed:
        st.warning("Применимость не подтверждена: расчёт и сохранение доступны, но результат будет помечен предупреждением.")

    if st.button("Сохранить расчёт в научный журнал", type="primary", width="stretch", key="save_thermobarometry_run"):
        try:
            saved = save_run(
                project_id,
                method_id=PUTIRKA_2008_CPX_T32D.method_id,
                source_dataframe=selection,
                results_dataframe=result,
                assumptions={
                    "pressure_kbar": float(pressure),
                    "applicability_confirmation": bool(confirmed),
                    "fe_policy": "FeOt only; no implicit Fe3+/Fe2+ reconstruction",
                    "qc_gate": "Cation sum (6 O) 3.99–4.02",
                    "advisory_policy": ADVISORY_POLICY_ID,
                },
            )
        except Exception as exc:
            st.error(f"Расчёт не сохранён: {exc}")
        else:
            st.success(f"Сохранён run #{saved.id}. Исходные анализы не изменялись.")
            st.rerun()

    csv = display.to_csv(index=False).encode("utf-8-sig")
    st.download_button(
        "Скачать текущую таблицу QC и T (CSV)", data=io.BytesIO(csv),
        file_name="petrolab_putirka_2008_cpx_eq32d.csv", mime="text/csv", width="stretch",
    )
    _run_history(project_id)
