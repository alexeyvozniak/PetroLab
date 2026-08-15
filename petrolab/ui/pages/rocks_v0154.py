"""Whole-rock page wrapper with the shared v0.15.4 staging importer."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from petrolab.column_schema import describe_header
from petrolab.import_staging import detect_role_columns
from petrolab.io_utils import normalize_columns_with_map
from petrolab.rock_staged_service import import_staged_rocks
from petrolab.sample_registry import list_samples
from petrolab.source_registry import list_studies
from petrolab.ui.layout import render_badges, render_hint
from petrolab.ui.staging_editor import render_staging_editor

from . import rocks as _rocks


def _read_table(uploaded) -> tuple[pd.DataFrame, str]:
    suffix = Path(uploaded.name).suffix.lower()
    content = uploaded.getvalue()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        workbook = pd.ExcelFile(io.BytesIO(content))
        sheet = st.selectbox("Лист", workbook.sheet_names, key="rock_v0154_sheet")
        return pd.read_excel(io.BytesIO(content), sheet_name=sheet), str(sheet)
    c1, c2 = st.columns(2)
    separator_name = c1.selectbox(
        "Разделитель",
        ["Определить автоматически", "Запятая", "Точка с запятой", "Табуляция"],
        key="rock_v0154_separator",
    )
    decimal_name = c2.selectbox("Десятичный знак", ["Точка", "Запятая"], key="rock_v0154_decimal")
    separators = {
        "Определить автоматически": None,
        "Запятая": ",",
        "Точка с запятой": ";",
        "Табуляция": "\t",
    }
    separator = separators[separator_name]
    frame = pd.read_csv(
        io.BytesIO(content),
        sep=separator,
        engine="python" if separator is None else "c",
        decimal="." if decimal_name == "Точка" else ",",
    )
    return frame, "CSV"


def _canonicalize_roles(frame: pd.DataFrame, role_map: dict[str, str]) -> pd.DataFrame:
    result = frame.copy()
    for role, source in role_map.items():
        if source in result.columns and role != source:
            result[role] = result[source]
    return result


def _existing_source_labels(project_id: int) -> list[str]:
    labels: list[str] = []
    for study in list_studies(int(project_id)):
        label = str(study.get("citation") or study.get("title") or study.get("doi") or "").strip()
        if label:
            labels.append(label)
    return labels


def _confirmation_ids(project_id: int, sample_names: dict[str, str], source_names: dict[str, str]) -> tuple[dict[str, int], dict[str, int]]:
    sample_by_name = {str(item["name"]): int(item["id"]) for item in list_samples(int(project_id))}
    source_by_name: dict[str, int] = {}
    for study in list_studies(int(project_id)):
        label = str(study.get("citation") or study.get("title") or study.get("doi") or "").strip()
        if label:
            source_by_name[label] = int(study["id"])
    return (
        {incoming: sample_by_name[canonical] for incoming, canonical in sample_names.items() if canonical in sample_by_name},
        {incoming: source_by_name[canonical] for incoming, canonical in source_names.items() if canonical in source_by_name},
    )


def _staged_bulk_import(project_id: int, legacy_import: Callable[[int], None]) -> None:
    with st.expander("Импортировать таблицу валовых составов", expanded=False):
        mode = st.radio(
            "Режим",
            ["Универсальный staging", "Быстрый старый импорт"],
            horizontal=True,
            key="rock_v0154_import_mode",
        )
        if mode == "Быстрый старый импорт":
            render_hint("Подходит для уже аккуратной таблицы: одна строка = один уникальный образец, без сложных блоков и сборных источников.")
            legacy_import(int(project_id))
            return

        render_hint(
            "Staging подходит для своих и литературных whole-rock таблиц: блоки, разные источники, повторные определения, "
            "русские/английские названия и произвольные метаданные исправляются до записи в базу."
        )
        uploaded = st.file_uploader(
            "Excel/CSV с породами",
            type=["xlsx", "xlsm", "xls", "csv", "tsv"],
            key="rock_v0154_upload",
        )
        if uploaded is None:
            return
        try:
            raw, sheet = _read_table(uploaded)
            raw = raw.dropna(how="all").reset_index(drop=True)
            frame, _ = normalize_columns_with_map(raw)
        except Exception as exc:
            st.error(f"Не удалось прочитать таблицу: {exc}")
            return
        if frame.empty:
            st.warning("Таблица пуста.")
            return

        chemistry = [
            str(column) for column in frame.columns
            if describe_header(column).quantity_kind in {
                "oxide", "trace_element", "element_concentration", "element_unknown_unit",
            }
        ]
        detected = detect_role_columns(frame.columns)
        if detected:
            st.caption("Автоматически распознано: " + " · ".join(f"{role} ← {column}" for role, column in detected.items()))

        existing_samples = [str(item["name"]) for item in list_samples(int(project_id))]
        existing_sources = _existing_source_labels(int(project_id))
        result, sample_names, source_names = render_staging_editor(
            frame,
            token=f"rock_{uploaded.name}",
            sheet=sheet,
            chemistry_columns=chemistry,
            existing_samples=existing_samples,
            existing_sources=existing_sources,
        )
        staged = _canonicalize_roles(result.dataframe, result.role_columns)
        if "Sample" not in staged.columns:
            st.warning("Назначьте колонку Sample или создайте поле Sample массовым действием — без физического образца импорт пород не выполняется.")
            return

        sources = len({str(value).strip() for value in staged.get("Source", pd.Series(dtype=str)).dropna().tolist() if str(value).strip()})
        samples = len({str(value).strip() for value in staged["Sample"].dropna().tolist() if str(value).strip()})
        render_badges([
            (f"строк · {len(staged)}", "neutral"),
            (f"образцов · {samples}", "accent"),
            (f"источников · {sources}", "neutral"),
            (f"химических полей · {len(chemistry)}", "success"),
        ])
        st.dataframe(staged.head(100), hide_index=True, width="stretch", height=min(460, 45 + 32 * min(100, len(staged))))

        if st.button("Импортировать whole-rock staging", type="primary", width="stretch", key="rock_v0154_save"):
            confirmed_samples, confirmed_sources = _confirmation_ids(
                int(project_id), sample_names, source_names,
            )
            try:
                imported = import_staged_rocks(
                    staged,
                    project_id=int(project_id),
                    source_file=uploaded.name,
                    source_sheet=sheet,
                    confirmed_samples=confirmed_samples,
                    confirmed_sources=confirmed_sources,
                )
            except Exception as exc:
                st.error(f"Импорт пород остановлен: {exc}")
                return
            st.success(
                f"Физических образцов: {len(imported.rock_ids)} · новых: {imported.created_rocks} · "
                f"повторно использовано: {imported.reused_rocks} · определений состава: {len(imported.determination_ids)}."
            )
            if imported.source_links:
                st.caption(f"Связей с литературными источниками: {imported.source_links}.")
            if imported.custom_attributes:
                st.caption(f"Сохранено пользовательских метаполей: {imported.custom_attributes}.")
            if imported.warnings:
                st.warning("\n".join(imported.warnings[:30]))
            st.rerun()


def render_rocks_page() -> None:
    original = _rocks._render_bulk_import

    def replacement(project_id: int) -> None:
        _staged_bulk_import(int(project_id), original)

    _rocks._render_bulk_import = replacement
    try:
        _rocks.render_rocks_page()
    finally:
        _rocks._render_bulk_import = original
