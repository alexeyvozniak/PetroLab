from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_datasets, load_dataset_dataframe
from petrolab.derived import formula_status, save_formula_results
from petrolab.minerals.classification import CLASSIFICATION_COLUMNS
from petrolab.minerals.formulae import methods_for
from petrolab.services.formula_service import calculate_formula_safe
from petrolab.ui.components import render_project_selector


def _derived_columns(source: pd.DataFrame, result: pd.DataFrame) -> list[str]:
    return [
        str(column)
        for column in result.columns
        if column not in source.columns and not str(column).startswith("_")
    ]


def _identity_columns(dataframe: pd.DataFrame) -> list[str]:
    return [
        column for column in ("Sample", "Grain", "Point", "Generation")
        if column in dataframe.columns
    ]


def _render_classification_summary(result: pd.DataFrame) -> None:
    columns = [column for column in CLASSIFICATION_COLUMNS if column in result.columns]
    if not columns:
        return
    identity = _identity_columns(result)
    st.subheader("Автоматическая классификация")
    st.caption(
        "Название вида показывается только там, где текущего пересчёта достаточно. "
        "Композиционное поле или диагностическая проекция не подменяются формальным IMA-именем."
    )
    st.dataframe(
        result[identity + columns].head(1000),
        width="stretch",
        hide_index=True,
        height=min(420, 42 + 35 * min(len(result), 10)),
    )


def render_formulae_page() -> None:
    st.title("Расчёты и структурные формулы")
    st.caption(
        "Расчётные величины и автоматическая классификация хранятся отдельно от исходного Excel. "
        "После сохранения они сразу доступны в «Единой базе» и «Диаграммах»."
    )

    project = render_project_selector("formula_project")
    if project is None:
        return
    datasets = list_datasets(int(project["id"]))
    if not datasets:
        st.info("В проекте пока нет анализов.")
        return

    mapping = {dataset_label(dataset): dataset for dataset in datasets}
    chosen = mapping[st.selectbox("Набор данных", list(mapping), key="formula_dataset")]
    dataset_id = int(chosen["id"])
    methods = methods_for(chosen["mineral_key"])
    if not methods:
        st.warning("Для этого минерала пока нет валидированного минералоспецифического пересчёта.")
        return

    method_map = {method.id: method for method in methods}
    method_id = st.selectbox(
        "Метод пересчёта",
        list(method_map),
        format_func=lambda value: method_map[value].title_ru,
        key="formula_method",
    )
    method = method_map[method_id]

    with st.expander("Что именно делает этот метод", expanded=False):
        st.write(f"**Нормировка:** {method.normalization_ru}")
        st.write(f"**Допущения:** {method.assumptions_ru}")
        if method.warning_ru:
            st.warning(method.warning_ru)
        if method.references:
            st.write("**Основные источники:**")
            for reference in method.references:
                st.caption("• " + reference)
        if method.recent_examples:
            st.write("**Примеры применения:**")
            for reference in method.recent_examples:
                st.caption("• " + reference)

    source = load_dataset_dataframe(dataset_id, include_meta=True)
    if source.empty:
        st.info("В выбранном наборе нет аналитических строк.")
        return

    try:
        result = calculate_formula_safe(source, chosen["mineral_key"], method.id)
    except Exception as exc:
        st.error(f"Пересчёт остановлен: {exc}")
        return

    derived = _derived_columns(source, result.data)
    status = formula_status(dataset_id)
    s1, s2, s3 = st.columns(3)
    s1.metric("Анализов", len(source))
    s2.metric("Расчётных полей", len(derived))
    if status.has_active_formula:
        s3.metric("Актуально в базе", f"{status.current_rows}/{status.total_rows}")
    else:
        s3.metric("Актуально в базе", "не сохранено")

    if status.has_active_formula:
        if status.method_id == method.id and status.stale_rows == 0:
            st.success("Этот метод уже сохранён и актуален для всех текущих строк.")
        elif status.stale_rows:
            st.warning(
                f"Сохранённый пересчёт частично устарел: строк для пересчёта заново — {status.stale_rows}."
            )
        else:
            st.info(
                f"Сейчас в базе активен другой метод: {status.method_title or status.method_id}. "
                "Сохранение ниже сделает выбранный метод активным для этого набора."
            )

    if result.note_ru:
        st.info(result.note_ru)

    if derived:
        _render_classification_summary(result.data)

        st.subheader("Результаты пересчёта")
        identity = _identity_columns(result.data)
        table_columns = identity + derived
        st.dataframe(
            result.data[table_columns].head(1000),
            width="stretch",
            hide_index=True,
            height=520,
        )
        with st.expander("Показать исходные и расчётные данные вместе"):
            visible = [column for column in result.data.columns if not str(column).startswith("_")]
            st.dataframe(result.data[visible].head(500), width="stretch", hide_index=True, height=520)

        if st.button(
            "Сохранить результаты в рабочую базу",
            type="primary",
            key="save_formula_results",
            width="stretch",
        ):
            saved = save_formula_results(
                dataset_id=dataset_id,
                mineral_key=chosen["mineral_key"],
                method_id=method.id,
                method_title=method.title_ru,
                source_dataframe=source,
                result_dataframe=result.data,
            )
            st.success(
                f"Сохранено {len(saved.derived_columns)} расчётных полей для {saved.row_count} анализов. "
                "Их уже можно выбирать как оси/фильтры в «Диаграммах»."
            )
            st.rerun()
    else:
        st.warning("Метод не создал новых расчётных колонок для этого набора.")
