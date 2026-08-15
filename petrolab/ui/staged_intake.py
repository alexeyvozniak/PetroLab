from __future__ import annotations

from pathlib import Path
from typing import Callable, Mapping

import pandas as pd
import streamlit as st

from petrolab.auto_pipeline import auto_process_imported_datasets
from petrolab.db import get_or_create_library_project, link_dataset_to_project
from petrolab.import_staging import detect_block_header_rows, source_like_column
from petrolab.row_provenance import materialize_dataset_row_provenance
from petrolab.sample_registry import add_sample_alias, list_samples
from petrolab.source_registry import list_studies
from petrolab.services.import_service import inspect_uploaded_sheet, list_uploaded_sheets, preview_uploaded_source
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


def _study_labels(project_id: int) -> list[str]:
    result: list[str] = []
    for study in list_studies(int(project_id)):
        label = str(study.get("citation") or study.get("title") or study.get("doi") or "").strip()
        if label:
            result.append(label)
    return result


def _confirmation_ids(
    project_id: int,
    sample_names: dict[str, str],
    source_names: dict[str, str],
) -> tuple[dict[str, int], dict[str, int]]:
    samples = {str(item["name"]): int(item["id"]) for item in list_samples(int(project_id))}
    sources: dict[str, int] = {}
    for study in list_studies(int(project_id)):
        label = str(study.get("citation") or study.get("title") or study.get("doi") or "").strip()
        if label:
            sources[label] = int(study["id"])
    return (
        {incoming: samples[canonical] for incoming, canonical in sample_names.items() if canonical in samples},
        {incoming: sources[canonical] for incoming, canonical in source_names.items() if canonical in sources},
    )


def _canonicalize_roles(frame: pd.DataFrame, roles: dict[str, str]) -> pd.DataFrame:
    result = frame.copy()
    for role, source in roles.items():
        if source in result.columns and role != source:
            result[role] = result[source]
    return result


def _replace_confirmed_names(
    frame: pd.DataFrame,
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


def _persist_sample_aliases(project_id: int, mappings: dict[str, str]) -> None:
    by_name = {str(item["name"]): int(item["id"]) for item in list_samples(int(project_id))}
    for alias, canonical in mappings.items():
        sample_id = by_name.get(str(canonical))
        if sample_id is not None and str(alias).strip() and str(alias).strip() != str(canonical).strip():
            add_sample_alias(sample_id, str(alias).strip(), source="staging_confirmed")


def _iron_semantics(previews: dict[str, object], token: str) -> tuple[dict[str, dict[str, str]], bool]:
    maps: dict[str, dict[str, str]] = {}
    ready = True
    for sheet, preview in previews.items():
        columns = {str(column) for column in preview.schema.columns}
        current: dict[str, str] = {}
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
                current[iron] = choices[choice]
        maps[sheet] = current
    return maps, ready


def _complexity_reasons(frame: pd.DataFrame, chemistry_columns: list[str]) -> list[str]:
    reasons: list[str] = []
    source = source_like_column(frame)
    if source and source in frame.columns:
        unique = {str(value).strip() for value in frame[source].dropna().tolist() if str(value).strip()}
        if len(unique) > 1:
            reasons.append(f"источников внутри листа: {len(unique)}")
    blocks = detect_block_header_rows(frame, chemistry_columns=chemistry_columns)
    if blocks:
        reasons.append(f"похожих на заголовки блоков строк: {len(blocks)}")
    return reasons


def _sheet_header_rows(selected: list[str], default_header: int, token: str) -> dict[str, int]:
    rows = {sheet: int(default_header) for sheet in selected}
    if len(selected) <= 1:
        return rows
    with st.expander("Строка заголовков по каждому листу", expanded=False):
        st.caption("У разных статей в одной книге заголовки могут начинаться на разных строках.")
        for index, sheet in enumerate(selected):
            rows[sheet] = int(st.number_input(
                f"{sheet or 'CSV'} · строка заголовков",
                min_value=1,
                max_value=200,
                value=int(default_header),
                step=1,
                key=f"v0154_sheet_header_{token}_{index}",
            ))
    return rows


def _structural_previews(
    data: bytes,
    filename: str,
    selected: list[str],
    header_rows: Mapping[str, int],
    previews: dict[str, object],
) -> tuple[dict[str, pd.DataFrame], list[str]]:
    frames: dict[str, pd.DataFrame] = {}
    complexity: list[str] = []
    if len(selected) > 1:
        complexity.append(
            f"выбрано листов: {len(selected)} — источник, строку заголовков и метаданные можно подтвердить отдельно для каждого"
        )
    for sheet in selected:
        preview = previews[sheet]
        frame = preview_uploaded_source(data, filename, sheet, int(header_rows[sheet]), "generic")
        frames[sheet] = frame
        chemistry = [item[1] for item in preview.recognized_oxides] + [item[1] for item in preview.recognized_traces]
        complexity.extend(f"{sheet or 'CSV'} · {reason}" for reason in _complexity_reasons(frame, chemistry))
    return frames, complexity


def render_table_import_v0154(
    original: Callable,
    project_id: int,
    name: str,
    data: bytes,
    token: str,
) -> list[int]:
    render_section_header(
        "Структура таблицы",
        "PetroLab сначала пытается понять файл сам; сложную структуру можно исправить до записи в базу",
    )
    try:
        sheets = list_uploaded_sheets(data, name)
    except Exception as exc:
        st.error(f"Файл не удалось открыть как таблицу: {exc}")
        return []

    default_header = int(st.number_input(
        "Строка заголовков по умолчанию",
        1, 200, 1, 1,
        key=f"v0154_header_{token}",
    ))
    selected = st.multiselect("Листы", sheets, default=sheets, key=f"v0154_sheets_{token}")
    if not selected:
        return []
    header_rows = _sheet_header_rows(selected, default_header, token)

    previews: dict[str, object] = {}
    try:
        for sheet in selected:
            previews[sheet] = inspect_uploaded_sheet(data, name, sheet, int(header_rows[sheet]))
        structural, complexity = _structural_previews(data, name, selected, header_rows, previews)
    except Exception as exc:
        st.error(f"Структуру таблицы не удалось проверить: {exc}")
        return []

    if complexity:
        render_badges([("сложная структура распознана", "warning")])
        for reason in complexity[:10]:
            st.caption("• " + reason)
    else:
        render_badges([("обычная таблица", "success")])

    mode = st.radio(
        "Как продолжить",
        ["Обычный безопасный импорт", "Разобрать перед импортом"],
        index=1 if complexity else 0,
        horizontal=True,
        key=f"v0154_mode_{token}",
        help=(
            "Обычный режим сохраняет двустороннюю синхронизацию XLSX. Staging позволяет менять структуру, "
            "но сохраняет исходный файл только как provenance и не переписывает его."
        ),
    )
    if mode == "Обычный безопасный импорт":
        # The established importer keeps its own per-sheet header/mineral controls and
        # asks the ambiguous Fe question exactly once.
        return render_table_import_with_provenance(original, project_id, name, data, token)

    measurement_maps, iron_ready = _iron_semantics(previews, token)
    if not iron_ready:
        st.info("Для staging нужно подтвердить неоднозначную форму представления железа.")
        return []

    normalized: dict[str, pd.DataFrame] = {}
    try:
        for sheet in selected:
            normalized[sheet] = preview_uploaded_source(
                data,
                name,
                sheet,
                int(header_rows[sheet]),
                "generic",
                measurement_map=measurement_maps.get(sheet, {}),
            )
    except Exception as exc:
        st.error(f"Нормализованный предпросмотр не построен: {exc}")
        return []

    render_hint(
        "Можно назначить Sample, Lithology, Source, Mineral, Generation, Method, Locality, Massif, возраст, координаты, "
        "лабораторию или любое своё поле сразу диапазону строк. Похожие имена объединяются только после подтверждения."
    )
    existing_samples = [str(item["name"]) for item in list_samples(int(project_id))]
    existing_sources = _study_labels(int(project_id))
    staged_frames: dict[str, pd.DataFrame] = {}
    sample_confirmations: dict[str, str] = {}
    source_confirmations: dict[str, str] = {}

    for sheet in selected:
        preview = previews[sheet]
        chemistry = [item[1] for item in preview.recognized_oxides] + [item[1] for item in preview.recognized_traces]
        with st.container(border=True):
            st.markdown(f"### {sheet or 'CSV'}")
            st.caption(f"Заголовки прочитаны со строки {int(header_rows[sheet])}.")
            if len(selected) > 1 and "Source" not in normalized[sheet].columns:
                st.caption(
                    "Если этот лист соответствует одной статье, выберите «Весь лист» → Source и назначьте источник одним действием."
                )
            result, sample_confirm, source_confirm = render_staging_editor(
                normalized[sheet],
                token=token,
                sheet=sheet or "CSV",
                chemistry_columns=chemistry,
                existing_samples=existing_samples,
                existing_sources=existing_sources,
            )
            staged_frames[sheet] = _canonicalize_roles(result.dataframe, result.role_columns)
            sample_confirmations.update(sample_confirm)
            source_confirmations.update(source_confirm)

    staged_frames = {
        sheet: _replace_confirmed_names(frame, sample_confirmations, source_confirmations)
        for sheet, frame in staged_frames.items()
    }
    dataset_name = st.text_input("Название набора", value=Path(name).stem, key=f"v0154_dataset_name_{token}")
    st.dataframe(
        pd.DataFrame([
            {
                "Лист": sheet or "CSV",
                "Строка заголовков": int(header_rows[sheet]),
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
        "Проверить и импортировать staging-копию",
        type="primary",
        width="stretch",
        key=f"v0154_import_{token}",
    ):
        return []

    try:
        library_project = get_or_create_library_project()
        imported = import_staged_frames(
            project_id=library_project,
            file_bytes=data,
            filename=name,
            frames=staged_frames,
            dataset_name=dataset_name,
            mineral_key="generic",
            header_rows={sheet: int(header_rows[sheet]) for sheet in staged_frames},
        )
        for dataset_id in imported.dataset_ids:
            link_dataset_to_project(project_id, dataset_id, "Добавлено через staging-импорт", purpose="working")
        confirmed_samples, confirmed_sources = _confirmation_ids(
            project_id, sample_confirmations, source_confirmations
        )
        provenance = materialize_dataset_row_provenance(
            project_id,
            imported.dataset_ids,
            sample_column="Sample" if any("Sample" in frame.columns for frame in staged_frames.values()) else None,
            source_column="Source" if any("Source" in frame.columns for frame in staged_frames.values()) else None,
            confirmed_samples=confirmed_samples,
            confirmed_sources=confirmed_sources,
        )
        _persist_sample_aliases(project_id, sample_confirmations)
        report = auto_process_imported_datasets(project_id, list(imported.dataset_ids))
        working = list(report.working_dataset_ids) or [int(value) for value in imported.dataset_ids]
        st.session_state[f"universal_imported_{token}"] = working
        st.session_state["workflow_recent_dataset_ids"] = working
        st.session_state["workflow_recent_import_target"] = project_id
    except Exception as exc:
        st.error(f"Staging-импорт остановлен: {exc}")
        return []

    st.success(
        f"Связей Sample: {provenance['sample_links']} · Source: {provenance['source_links']} · рабочих наборов: {len(working)}."
    )
    st.rerun()
    return []
