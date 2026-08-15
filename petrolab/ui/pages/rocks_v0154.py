"""Whole-rock page wrapper with the shared universal staging importer."""
from __future__ import annotations

import io
from pathlib import Path
from typing import Callable, Mapping

import pandas as pd
import streamlit as st

from petrolab.column_schema import describe_header
from petrolab.import_staging import detect_role_columns
from petrolab.io_utils import normalize_columns_with_map
from petrolab.repositories.rock_repository import list_rocks
from petrolab.rock_staged_service import import_staged_rocks
from petrolab.sample_registry import add_sample_alias, list_samples
from petrolab.source_registry import list_studies
from petrolab.term_registry import DEFAULT_TERM_DOMAINS, persist_staged_terms, term_values
from petrolab.ui.layout import render_badges, render_hint
from petrolab.ui.staging_editor import render_staging_editor

from . import rocks as _rocks


_IRON_CHOICES = {
    "FeO": {
        "Всё железо, выраженное как FeO total": "FeOt",
        "Отдельно измеренное Fe²⁺ как FeO": "FeO",
    },
    "Fe2O3": {
        "Всё железо, выраженное как Fe₂O₃ total": "Fe2O3t",
        "Отдельно измеренное Fe³⁺ как Fe₂O₃": "Fe2O3",
    },
}


def _read_table(uploaded) -> tuple[pd.DataFrame, str]:
    suffix = Path(uploaded.name).suffix.lower()
    content = uploaded.getvalue()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        workbook = pd.ExcelFile(io.BytesIO(content))
        sheet = st.selectbox("Лист", workbook.sheet_names, key="rock_staging_sheet")
        return pd.read_excel(io.BytesIO(content), sheet_name=sheet), str(sheet)
    left, right = st.columns(2)
    separator_name = left.selectbox(
        "Разделитель",
        ["Определить автоматически", "Запятая", "Точка с запятой", "Табуляция"],
        key="rock_staging_separator",
    )
    decimal_name = right.selectbox("Десятичный знак", ["Точка", "Запятая"], key="rock_staging_decimal")
    separators = {
        "Определить автоматически": None,
        "Запятая": ",",
        "Точка с запятой": ";",
        "Табуляция": "\t",
    }
    separator = separators[separator_name]
    return (
        pd.read_csv(
            io.BytesIO(content),
            sep=separator,
            engine="python" if separator is None else "c",
            decimal="." if decimal_name == "Точка" else ",",
        ),
        "CSV",
    )


def _canonicalize_roles(frame: pd.DataFrame, role_map: Mapping[str, str]) -> pd.DataFrame:
    result = frame.copy()
    for role, source in role_map.items():
        if source in result.columns and role != source:
            result[role] = result[source]
    return result


def _replace_confirmed_values(
    frame: pd.DataFrame,
    confirmations: Mapping[str, Mapping[str, str]],
) -> pd.DataFrame:
    result = frame.copy()
    for field, mapping in confirmations.items():
        if field not in result.columns or not mapping:
            continue
        original = result[field].copy()
        mapped = original.map(
            lambda value: mapping.get(str(value).strip(), value)
            if pd.notna(value) and str(value).strip() else value
        )
        changed = original.astype("string").fillna("") != mapped.astype("string").fillna("")
        if bool(changed.any()):
            source_field = f"{field} (source)"
            if source_field not in result.columns:
                result[source_field] = original
            result[field] = mapped
    return result


def _apply_iron_semantics(frame: pd.DataFrame, token: str) -> tuple[pd.DataFrame, bool]:
    result = frame.copy()
    ready = True
    for source, choices in _IRON_CHOICES.items():
        if source not in result.columns:
            continue
        choice = st.radio(
            f"Что означает {source} в whole-rock таблице?",
            list(choices),
            index=None,
            key=f"rock_staging_iron_{token}_{source}",
        )
        if choice is None:
            ready = False
            continue
        target = choices[choice]
        if target != source:
            if target in result.columns:
                st.error(f"Нельзя преобразовать {source} → {target}: колонка {target} уже существует.")
                ready = False
                continue
            result = result.rename(columns={source: target})
    return result, ready


def _existing_source_labels(project_id: int) -> list[str]:
    labels: list[str] = []
    for study in list_studies(int(project_id)):
        label = str(study.get("citation") or study.get("title") or study.get("doi") or "").strip()
        if label:
            labels.append(label)
    return labels


def _existing_terms(project_id: int) -> dict[str, list[str]]:
    """Seed alias suggestions from both the new term dictionary and existing rock passports."""
    values = {domain: list(term_values(int(project_id), domain)) for domain in DEFAULT_TERM_DOMAINS}
    passport_map = {
        "Lithology": "lithology",
        "Method": "chemistry_method",
        "Laboratory": "laboratory",
        "Locality": "locality",
        "Massif": "massif",
    }
    for rock in list_rocks(int(project_id)):
        for domain, field in passport_map.items():
            value = str(rock.get(field) or "").strip()
            if value and value not in values[domain]:
                values[domain].append(value)
    return values


def _confirmation_ids(
    project_id: int,
    sample_names: Mapping[str, str],
    source_names: Mapping[str, str],
) -> tuple[dict[str, int], dict[str, int]]:
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


def _persist_sample_aliases(project_id: int, mappings: Mapping[str, str]) -> None:
    by_name = {str(item["name"]): int(item["id"]) for item in list_samples(int(project_id))}
    for alias, canonical in mappings.items():
        sample_id = by_name.get(str(canonical))
        if sample_id is not None and str(alias).strip() and str(alias).strip() != str(canonical).strip():
            add_sample_alias(int(sample_id), str(alias).strip(), source="staging_confirmed")


def _staged_bulk_import(project_id: int, legacy_import: Callable[[int], None]) -> None:
    with st.expander("Импортировать таблицу валовых составов", expanded=False):
        mode = st.radio(
            "Режим",
            ["Универсальный staging", "Быстрый старый импорт"],
            horizontal=True,
            key="rock_staging_import_mode",
        )
        if mode == "Быстрый старый импорт":
            render_hint(
                "Подходит для уже аккуратной таблицы: одна строка = один уникальный образец, без сложных блоков и сборных источников."
            )
            legacy_import(int(project_id))
            return

        render_hint(
            "Staging подходит для своих и литературных whole-rock таблиц: блоки, разные источники, повторные определения, "
            "русские/английские названия и произвольные метаданные исправляются до записи в базу."
        )
        uploaded = st.file_uploader(
            "Excel/CSV с породами",
            type=["xlsx", "xlsm", "xls", "csv", "tsv"],
            key="rock_staging_upload",
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

        frame, iron_ready = _apply_iron_semantics(frame, f"{uploaded.name}_{sheet}")
        if not iron_ready:
            st.info("Перед импортом нужно подтвердить форму представления железа.")
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

        result, _, _ = render_staging_editor(
            frame,
            token=f"rock_{uploaded.name}",
            sheet=sheet,
            chemistry_columns=chemistry,
            existing_samples=[str(item["name"]) for item in list_samples(int(project_id))],
            existing_sources=_existing_source_labels(int(project_id)),
            existing_terms=_existing_terms(int(project_id)),
        )
        staged = _canonicalize_roles(result.dataframe, result.role_columns)
        staged = _replace_confirmed_values(staged, result.confirmations)
        if "Sample" not in staged.columns:
            st.warning(
                "Назначьте колонку Sample или создайте поле Sample массовым действием — без физического образца импорт пород не выполняется."
            )
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

        if not st.button("Импортировать whole-rock staging", type="primary", width="stretch", key="rock_staging_save"):
            return

        sample_names = result.confirmations.get("Sample", {})
        source_names = result.confirmations.get("Source", {})
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
            _persist_sample_aliases(int(project_id), sample_names)
            remembered_terms = persist_staged_terms(int(project_id), staged, result.confirmations)
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
        if remembered_terms:
            st.caption(f"Канонических терминов/категорий запомнено: {remembered_terms}.")
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
