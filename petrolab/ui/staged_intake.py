from __future__ import annotations

from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from petrolab.auto_pipeline import auto_process_imported_datasets
from petrolab.db import get_or_create_library_project, link_dataset_to_project
from petrolab.import_staging import detect_block_header_rows, source_like_column
from petrolab.row_provenance import materialize_dataset_row_provenance
from petrolab.sample_registry import add_sample_alias, list_samples
from petrolab.source_registry import list_studies
from petrolab.services.import_service import (
    inspect_uploaded_sheet,
    list_uploaded_sheets,
    preview_uploaded_source,
)
from petrolab.staged_import_service import import_staged_frames
from petrolab.ui.layout import render_badges, render_hint, render_section_header
from petrolab.ui.staging_editor import render_staging_editor
from petrolab.ui.universal_intake_extensions import render_table_import_with_provenance


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


def _source_labels(project_id: int) -> list[str]:
    labels: list[str] = []
    for study in list_studies(int(project_id)):
        value = str(study.get("citation") or study.get("title") or study.get("doi") or "").strip()
        if value:
            labels.append(value)
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


def _canonicalize_staging_roles(frame: pd.DataFrame, roles: dict[str, str]) -> pd.DataFrame:
    result = frame.copy()
    for role, source in roles.items():
        if source not in result.columns:
            continue
        if role == source:
            continue
        # Keep the author's original column and add a canonical working field.
        result[role] = result[source]
    return result


def _replace_confirmed_names(
    frame: pd.DataFrame,
    *,
    sample_names: dict[str, str],
    source_names: dict[str, str],
) -> pd.DataFrame:
    result = frame.copy()
    for field, mapping in (("Sample", sample_names), ("Source", source_names)):
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


def _persist_confirmed_sample_aliases(project_id: int, mappings: dict[str, str]) -> None:
    if not mappings:
        return
    by_name = {str(item["name"]): int(item["id"]) for item in list_samples(int(project_id))}
    for alias, canonical in mappings.items():
        sample_id = by_name.get(str(canonical))
        if sample_id is not None and str(alias).strip() and str(alias).strip() != str(canonical).strip():
            add_sample_alias(int(sample_id), str(alias).strip(), source="staging_confirmed")


def _iron_semantics(previews: dict[str, object], token: str) -> tuple[dict[str, dict[str, str]], bool]:
    result: dict[str, dict[str, str]] = {}
    ready = True
    for sheet, preview in previews.items():
        columns = {str(column) for column in preview.schema.columns}
        mapping: dict[str, str] = {}
        for iron, choices in _IRON_CHOICES.items():
            if iron not in columns:
                continue
            choice = st.radio(
                f"{sheet or 'CSV'} · что означает {iron}?",
                list(choices),
                index=None,
                key=f"v0154_iron_{token}_{sheet}_{iron}",
            )
            if choice is None:
                ready = False
            else:
                mapping[iron] = choices[choice]
        result[sheet] = mapping
    return result, ready


def _complexity_reasons(frame: pd.DataFrame, chemistry_columns: list[str]) -> list[str]:
    reasons: list[str] = []
    source = source_like_column(frame)
    if source and source in frame.columns:
        unique = {
            str(value).strip() for value in frame[source].dropna().tolist() if str(value).strip()
        }
        if len(unique) > 1:
            reasons.append(f"в одном листе найдено источников: {len(unique)}")
    blocks = detect_block_header_rows(frame, chemistry_columns=chemistry_columns)
    if blocks:
        reasons.append(f"похожих на заголовки блоков строк: {len(blocks)}")
    return reasons


def render_table_import_v0154(
    original: Callable,
    project_id: int,
    name: str,
    data: bytes,
    token: str,
) -> list[int]:
    """Use the old safe path for ordinary tables and staging for complex structures."""
    render_section_header(
        "Структура таблицы",
        "PetroLab сначала пытается понять файл сам; сложную структуру можно исправить до записи в базу",
    )
    try:
        sheets = list_uploaded_sheets(data, name)
    except Exception as exc:
        st.error(f"Файл не удалось открыть как таблицу: {exc}")
        return []

    header_row = int(st.number_input(
        "Строка заголовков для структурного анализа",
        min_value=1, max_value=200, value=1, step=1,
        key=f"v0154_header_{token}",
    ))
    selected = st.multiselect(
        "Листы",
        sheets,
        default=sheets,
        key=f"v0154_sheets_{token}",
    )
    if not selected:
        return []

    previews: dict[str, object] = {}
    for sheet in selected:
        try:
            previews[sheet] = inspect_uploaded_sheet(data, name, sheet, header_row)
        except Exception as exc:
            st.error(f"{sheet or 'CSV'}: не удалось прочитать схему — {exc}")
            return []

    measurement_maps, iron_ready = _iron_semantics(previews, token)
    if not iron_ready:
        st.info("Нужно подтвердить только неоднозначную форму представления железа; после этого структурный предпросмотр продолжится.")
        return []

    normalized: dict[str, pd.DataFrame] = {}
    complexity: list[str] = []
    for sheet in selected:
        preview = previews[sheet]
        try:
            frame = preview_uploaded_source(
                data, name, sheet, header_row, "generic",
                measurement_map=measurement_maps.get(sheet, {}),
            )
        except Exception as exc:
            st.error(f"{sheet or 'CSV'}: не удалось построить структурный предпросмотр — {exc}")
            return []
        normalized[sheet] = frame
        chemistry = [item[1] for item in preview.recognized_oxides] + [item[1] for item in preview.recognized_traces]
        complexity.extend(f"{sheet or 'CSV'} · {reason}" for reason in _complexity_reasons(frame, chemistry))

    if complexity:
        render_badges([("сложная структура распознана", "warning")])
        for reason in complexity[:8]:
            st.caption("• " + reason)
    else:
        render_badges([("обычная таблица", "success")])

    default_mode = "Разобрать перед импортом" if complexity else "Обычный безопасный импорт"
    mode = st.radio(
        "Как продолжить",
        ["Обычный безопасный импорт", "Разобрать перед импортом"],
        index=1 if default_mode == "Разобрать перед импортом" else 0,
        horizontal=True,
        key=f"v0154_mode_{token}",
        help="Обычный режим сохраняет текущую двустороннюю синхронизацию XLSX. Staging создаёт безопасную нормализованную копию и не переписывает исходник.",
    )
    if mode == "Обычный безопасный импорт":
        return render_table_import_with_provenance(original, project_id, name, data, token)

    render_hint(
        "В staging можно назначить Sample, Lithology, Source, Mineral, Generation, Method, Locality, Massif или любое своё поле сразу диапазону строк. "
        "После подтверждения похожие названия сохраняются как один канонический объект с алиасами."
    )
    existing_samples = [str(item["name"]) for item in list_samples(int(project_id))]
    existing_sources = _source_labels(int(project_id))
    staged_frames: dict[str, pd.DataFrame] = {}
    sample_name_confirmations: dict[str, str] = {}
    source_name_confirmations: dict[str, str] = {}

    for sheet in selected:
        preview = previews[sheet]
        chemistry = [item[1] for item in preview.recognized_oxides] + [item[1] for item in preview.recognized_traces]
        with st.container(border=True):
            st.markdown(f"### {sheet or 'CSV'}")
            result, sample_confirm, source_confirm = render_staging_editor(
                normalized[sheet],
                token=token,
                sheet=sheet or "CSV",
                chemistry_columns=chemistry,
                existing_samples=existing_samples,
                existing_sources=existing_sources,
            )
            frame = _canonicalize_staging_roles(result.dataframe, result.role_columns)
            staged_frames[sheet] = frame
            sample_name_confirmations.update(sample_confirm)
            source_name_confirmations.update(source_confirm)

    staged_frames = {
        sheet: _replace_confirmed_names(
            frame,
            sample_names=sample_name_confirmations,
            source_names=source_name_confirmations,
        )
        for sheet, frame in staged_frames.items()
    }

    dataset_name = st.text_input(
        "Название набора",
        value=Path(name).stem,
        key=f"v0154_dataset_name_{token}",
    )
    summary = pd.DataFrame([
        {
            "Лист": sheet or "CSV",
            "Строк после staging": len(frame),
            "Sample": "Sample" in frame.columns,
            "Lithology": "Lithology" in frame.columns,
            "Source": "Source" in frame.columns,
        }
        for sheet, frame in staged_frames.items()
    ])
    st.dataframe(summary, hide_index=True, width="stretch")

    if st.button(
        "Проверить и импортировать staging-копию",
        type="primary",
        width="stretch",
        key=f"v0154_import_{token}",
    ):
        library_project = get_or_create_library_project()
        try:
            imported = import_staged_frames(
                project_id=int(library_project),
                file_bytes=data,
                filename=name,
                frames=staged_frames,
                dataset_name=dataset_name,
                mineral_key="generic",
                header_rows={sheet: header_row for sheet in staged_frames},
            )
            for dataset_id in imported.dataset_ids:
                link_dataset_to_project(
                    int(project_id), int(dataset_id),
                    "Добавлено через staging-импорт",
                    purpose="working",
                )
            confirmed_samples, confirmed_sources = _confirmation_ids(
                int(project_id), sample_name_confirmations, source_name_confirmations,
            )
            provenance = materialize_dataset_row_provenance(
                int(project_id),
                imported.dataset_ids,
                sample_column="Sample" if any("Sample" in frame.columns for frame in staged_frames.values()) else None,
                source_column="Source" if any("Source" in frame.columns for frame in staged_frames.values()) else None,
                confirmed_samples=confirmed_samples,
                confirmed_sources=confirmed_sources,
            )
            _persist_confirmed_sample_aliases(int(project_id), sample_name_confirmations)
            report = auto_process_imported_datasets(int(project_id), list(imported.dataset_ids))
            working = list(report.working_dataset_ids) or [int(value) for value in imported.dataset_ids]
            st.session_state[f"universal_imported_{token}"] = working
            st.session_state["workflow_recent_dataset_ids"] = working
            st.session_state["workflow_recent_import_target"] = int(project_id)
        except Exception as exc:
            st.error(f"Staging-импорт остановлен: {exc}")
            return []
        st.success(
            f"Импортировано строковых связей: Sample — {provenance['sample_links']}, Source — {provenance['source_links']}. "
            f"Рабочих наборов: {len(working)}."
        )
        st.rerun()
    return []
