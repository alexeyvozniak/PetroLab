from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_datasets, load_dataset_dataframe
from petrolab.derived import formula_status, save_formula_results
from petrolab.minerals.classification import CLASSIFICATION_COLUMNS
from petrolab.minerals.formulae import methods_for
from petrolab.services.formula_service import calculate_formula_safe
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.project_context import active_project_id


def _derived_columns(source: pd.DataFrame, result: pd.DataFrame) -> list[str]:
    return [str(column) for column in result.columns if column not in source.columns and not str(column).startswith("_")]


def _identity_columns(dataframe: pd.DataFrame) -> list[str]:
    return [column for column in ("Sample", "Grain", "Point", "Generation") if column in dataframe.columns]


def _render_classification_summary(result: pd.DataFrame) -> None:
    columns = [column for column in CLASSIFICATION_COLUMNS if column in result.columns]
    if not columns:
        return
    render_section_header("Автоматическая классификация", "Формальное имя только при достаточных данных")
    st.dataframe(
        result[_identity_columns(result) + columns].head(1000),
        width="stretch", hide_index=True,
        height=min(420, 42 + 35 * min(len(result), 10)),
    )


def _render_full_validity_summary(result: pd.DataFrame) -> None:
    if "formula_valid" not in result.columns:
        return
    valid = result["formula_valid"].fillna(False).astype(bool)
    invalid = ~valid
    render_badges([
        (f"{int(valid.sum()):,} валидных формул".replace(",", " "), "success"),
        (f"{int(invalid.sum()):,} не рассчитаны".replace(",", " "), "warning" if invalid.any() else "neutral"),
    ])
    if invalid.any():
        problem_columns = _identity_columns(result) + [
            column for column in [
                "formula_invalid_reason", "QC formula input", "Formula missing inputs",
                "QC суммы", "QC химии", "QC железа",
            ] if column in result.columns
        ]
        st.markdown("#### Проблемные строки во всём наборе")
        st.caption(
            "Таблица строится по полному результату, а не только по первым строкам предпросмотра. "
            "Невалидные строки сохраняют source chemistry, но formula-derived поля для них остаются пустыми."
        )
        st.dataframe(
            result.loc[invalid, problem_columns].head(2000),
            width="stretch", hide_index=True, height=min(520, 45 + 28 * min(int(invalid.sum()), 16)),
        )
        if int(invalid.sum()) > 2000:
            st.caption(f"Показано 2000 из {int(invalid.sum())} проблемных строк.")


def render_formulae_page() -> None:
    render_page_header(
        "Расчёты",
        "Структурные формулы, APFU и end-members сохраняются отдельным слоем и не подменяют исходную химию.",
        eyebrow="Данные",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала создайте проект.")
        return
    datasets = list_datasets(project_id)
    if not datasets:
        st.info("В активном проекте пока нет анализов.")
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
        "Метод", list(method_map),
        format_func=lambda value: method_map[value].title_ru,
        key="formula_method",
    )
    method = method_map[method_id]
    with st.expander("Метод, допущения и источники", expanded=False):
        st.write(f"**Нормировка:** {method.normalization_ru}")
        st.write(f"**Допущения:** {method.assumptions_ru}")
        st.write("**Политика входов:** все распознанные измеренные oxide-columns участвуют в базовой формуле; фактический список сохраняется в provenance результата.")
        if method.warning_ru:
            st.warning(method.warning_ru)
        for reference in method.references:
            st.caption("• " + reference)

    source = load_dataset_dataframe(dataset_id, include_meta=True)
    if source.empty:
        st.info("В наборе нет аналитических строк.")
        return
    try:
        result = calculate_formula_safe(source, chosen["mineral_key"], method.id)
    except Exception as exc:
        st.error(f"Пересчёт остановлен: {exc}")
        return

    derived = _derived_columns(source, result.data)
    status = formula_status(dataset_id)
    status_badges = [
        (f"{len(source)} анализов", "neutral"),
        (f"{len(derived)} расчётных полей", "accent"),
    ]
    if status.has_active_formula and status.method_id == method.id:
        status_badges.extend([
            (f"Актуально: {status.current_rows}/{status.total_rows}", "success" if status.stale_rows == 0 else "warning"),
            (f"Валидно: {status.valid_rows}", "success" if status.invalid_rows == 0 else "warning"),
            (f"Не рассчитано: {status.invalid_rows}", "warning" if status.invalid_rows else "neutral"),
        ])
        if status.unknown_validity_rows:
            status_badges.append((f"Старые результаты без validity: {status.unknown_validity_rows}", "warning"))
    else:
        status_badges.append(("○ Не сохранён для этого метода", "neutral"))
    render_badges(status_badges)

    if status.has_active_formula and status.method_id != method.id:
        st.caption(f"Сейчас активен другой метод: {status.method_title or status.method_id}.")
    if result.note_ru:
        st.caption(result.note_ru)
    if not derived:
        st.warning("Метод не создал новых расчётных колонок для этого набора.")
        return

    _render_full_validity_summary(result.data)
    _render_classification_summary(result.data)
    render_section_header("Результаты", "Предпросмотр первых 1000 строк; validity summary выше относится ко всему набору")
    identity = _identity_columns(result.data)
    st.dataframe(result.data[identity + derived].head(1000), width="stretch", hide_index=True, height=520)
    with st.expander("Исходные и расчётные данные вместе"):
        visible = [column for column in result.data.columns if not str(column).startswith("_")]
        st.dataframe(result.data[visible].head(500), width="stretch", hide_index=True, height=520)

    st.markdown('<div class="petrolab-export-zone"></div>', unsafe_allow_html=True)
    if st.button("Сохранить расчёт в рабочую базу", type="primary", key="save_formula_results", width="stretch"):
        saved = save_formula_results(
            dataset_id=dataset_id,
            mineral_key=chosen["mineral_key"],
            method_id=method.id,
            method_title=method.title_ru,
            source_dataframe=source,
            result_dataframe=result.data,
        )
        st.success(f"Сохранено {len(saved.derived_columns)} полей для {saved.row_count} анализов.")
        st.rerun()
