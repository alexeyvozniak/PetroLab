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


def _read_tables(uploaded) -> dict[str, pd.DataFrame]:
    suffix = Path(uploaded.name).suffix.lower()
    content = uploaded.getvalue()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        workbook = pd.ExcelFile(io.BytesIO(content))
        selected = st.multiselect(
            "Листы",
            workbook.sheet_names,
            default=workbook.sheet_names,
            key="rock_staging_sheets",
        )
        return {
            str(sheet): pd.read_excel(io.BytesIO(content), sheet_name=sheet)
            for sheet in selected
        }

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
    frame = pd.read_csv(
        io.BytesIO(content),
        sep=separator,
        engine="python" if separator is None else "c",
        decimal="." if decimal_name == "Точка" else ",",
    )
    return {"CSV": frame}


def _canonicalize_roles(frame: pd.DataFrame, role_map: Mapping[str, str]) -> pd.DataFrame:
    result = frame.copy()
    for role, source in role_map.items():
        if source in result.columns and role != source:
            result[role] = result[source]
    return result


def _merge_confirmations(
    target: dict[str, dict[str, str]],
    incoming: Mapping[str, Mapping[str, str]],
) -> None:
    for field, mappings in incoming.items():
        target.setdefault(str(field), {}).update(
            {str(alias): str(canonical) for alias, canonical in mappings.items()}
        )


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
            f"Что означает {source}?",
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


def _extend_seen_values(
    frame: pd.DataFrame,
    sample_values: list[str],
    source_values: list[str],
    term_values_by_domain: dict[str, list[str]],
) -> None:
    if "Sample" in frame.columns:
        for value in frame["Sample"].dropna().astype(str):
            clean = value.strip()
            if clean and clean not in sample_values:
                sample_values.append(clean)
    if "Source" in frame.columns:
        for value in frame["Source"].dropna().astype(str):
            clean = value.strip()
            if clean and clean not in source_values:
                source_values.append(clean)
    for domain in DEFAULT_TERM_DOMAINS:
        if domain not in frame.columns:
            continue
        for value in frame[domain].dropna().astype(str):
            clean = value.strip()
            if clean and clean not in term_values_by_domain[domain]:
                term_values_by_domain[domain].append(clean)


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
            "Staging подходит для своих и литературных whole-rock таблиц: несколько листов, блоки, разные источники, "
            "повторные определения, русские/английские названия и произвольные метаданные исправляются до записи в базу."
        )
        uploaded = st.file_uploader(
            "Excel/CSV с породами",
            type=["xlsx", "xlsm", "xls", "csv", "tsv"],
            key="rock_staging_upload",
        )
        if uploaded is None:
            return

        try:
            raw_tables = _read_tables(uploaded)
        except Exception as exc:
            st.error(f"Не удалось прочитать таблицу: {exc}")
            return
        if not raw_tables:
            st.info("Выберите хотя бы один лист.")
            return

        existing_samples = [str(item["name"]) for item in list_samples(int(project_id))]
        existing_sources = _existing_source_labels(int(project_id))
        existing_terms = _existing_terms(int(project_id))
        staged_frames: dict[str, pd.DataFrame] = {}
        all_confirmations: dict[str, dict[str, str]] = {}
        all_ready = True

        for sheet, raw in raw_tables.items():
            with st.container(border=True):
                st.markdown(f"### {sheet}")
                try:
                    clean_raw = raw.dropna(how="all").reset_index(drop=True)
                    frame, _ = normalize_columns_with_map(clean_raw)
                except Exception as exc:
                    st.error(f"{sheet}: не удалось нормализовать таблицу — {exc}")
                    all_ready = False
                    continue
                if frame.empty:
                    st.warning("Лист пуст.")
                    continue

                frame, iron_ready = _apply_iron_semantics(frame, f"{uploaded.name}_{sheet}")
                if not iron_ready:
                    st.info("Подтвердите форму представления железа для этого листа.")
                    all_ready = False
                    continue

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
                    existing_samples=existing_samples,
                    existing_sources=existing_sources,
                    existing_terms=existing_terms,
                )
                staged = _canonicalize_roles(result.dataframe, result.role_columns)
                staged_frames[sheet] = staged
                _merge_confirmations(all_confirmations, result.confirmations)
                _extend_seen_values(staged, existing_samples, existing_sources, existing_terms)

        if not staged_frames:
            return

        staged_frames = {
            sheet: _replace_confirmed_values(frame, all_confirmations)
            for sheet, frame in staged_frames.items()
        }
        missing_sample = [sheet for sheet, frame in staged_frames.items() if "Sample" not in frame.columns]
        if missing_sample:
            st.warning(
                "Назначьте Sample на листах: " + ", ".join(missing_sample)
                + ". Без физического образца эти листы не будут импортированы."
            )
            all_ready = False

        total_rows = sum(len(frame) for frame in staged_frames.values())
        all_samples = {
            str(value).strip()
            for frame in staged_frames.values() if "Sample" in frame.columns
            for value in frame["Sample"].dropna().tolist() if str(value).strip()
        }
        all_sources = {
            str(value).strip()
            for frame in staged_frames.values() if "Source" in frame.columns
            for value in frame["Source"].dropna().tolist() if str(value).strip()
        }
        render_badges([
            (f"листов · {len(staged_frames)}", "neutral"),
            (f"строк · {total_rows}", "neutral"),
            (f"образцов · {len(all_samples)}", "accent"),
            (f"источников · {len(all_sources)}", "neutral"),
        ])
        st.dataframe(
            pd.DataFrame([
                {
                    "Лист": sheet,
                    "Строк": len(frame),
                    "Sample": "Sample" in frame.columns,
                    "Lithology": "Lithology" in frame.columns,
                    "Source": "Source" in frame.columns,
                }
                for sheet, frame in staged_frames.items()
            ]),
            hide_index=True,
            width="stretch",
        )

        if not st.button(
            "Импортировать whole-rock staging",
            type="primary",
            width="stretch",
            disabled=not all_ready,
            key="rock_staging_save",
        ):
            return

        sample_names = all_confirmations.get("Sample", {})
        source_names = all_confirmations.get("Source", {})
        confirmed_samples, confirmed_sources = _confirmation_ids(
            int(project_id), sample_names, source_names,
        )

        imported_rock_ids: set[int] = set()
        determination_count = created_count = reused_count = source_links = custom_attributes = 0
        warnings: list[str] = []
        remembered_terms = 0
        try:
            for sheet, staged in staged_frames.items():
                imported = import_staged_rocks(
                    staged,
                    project_id=int(project_id),
                    source_file=uploaded.name,
                    source_sheet=sheet,
                    confirmed_samples=confirmed_samples,
                    confirmed_sources=confirmed_sources,
                )
                imported_rock_ids.update(imported.rock_ids)
                determination_count += len(imported.determination_ids)
                created_count += imported.created_rocks
                reused_count += imported.reused_rocks
                source_links += imported.source_links
                custom_attributes += imported.custom_attributes
                warnings.extend(imported.warnings)
                remembered_terms += persist_staged_terms(int(project_id), staged, all_confirmations)
            _persist_sample_aliases(int(project_id), sample_names)
        except Exception as exc:
            st.error(f"Импорт пород остановлен: {exc}")
            return

        st.success(
            f"Физических образцов: {len(imported_rock_ids)} · новых: {created_count} · "
            f"повторно использовано: {reused_count} · определений состава: {determination_count}."
        )
        if source_links:
            st.caption(f"Связей с литературными источниками: {source_links}.")
        if custom_attributes:
            st.caption(f"Сохранено пользовательских метаполей: {custom_attributes}.")
        if remembered_terms:
            st.caption(f"Канонических терминов/категорий запомнено: {remembered_terms}.")
        if warnings:
            st.warning("\n".join(warnings[:30]))
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
