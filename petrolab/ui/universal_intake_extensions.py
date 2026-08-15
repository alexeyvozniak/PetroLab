"""Completion layer for the v0.15.1 universal intake workflow.

Adds source provenance (own/article/colleague) and lets every image in one batch
choose its own analytical dataset. This matters after automatic mixed-phase
splitting, where analyses from one workbook may live in several child datasets.
"""
from __future__ import annotations

import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Callable

import streamlit as st

from petrolab.db import list_accessible_datasets, load_dataset_dataframe
from petrolab.services.image_service import (
    ImageAssignment,
    create_assigned_image_batch,
    delete_image_asset,
    SCOPE_ANALYSIS,
    SCOPE_DATASET,
    SCOPE_FIELD,
)
from petrolab.source_registry import create_study, link_dataset_to_study
from petrolab.ui import universal_intake as base
from petrolab.ui.image_components import (
    IMAGE_KINDS,
    SCOPE_LABELS,
    assignment_error,
    render_field_controls,
    render_multi_point_controls,
)
from petrolab.ui.layout import render_badges, render_section_header


_SOURCE_OWN = "Мои анализы"
_SOURCE_ARTICLE = "Статья"
_SOURCE_COLLEAGUE = "Данные коллеги"
_SOURCE_OTHER = "Другой внешний источник"
_SOURCE_OPTIONS = (_SOURCE_OWN, _SOURCE_ARTICLE, _SOURCE_COLLEAGUE, _SOURCE_OTHER)
_SOURCE_TYPES = {
    _SOURCE_ARTICLE: "article",
    _SOURCE_COLLEAGUE: "colleague",
    _SOURCE_OTHER: "other",
}


def _source_controls(token: str, filename: str) -> dict:
    kind = st.radio(
        "Что это за таблица?",
        _SOURCE_OPTIONS,
        horizontal=True,
        key=f"universal_source_kind_{token}",
        help="Это provenance данных. PetroLab не пытается угадать автора или происхождение по имени файла.",
    )
    if kind == _SOURCE_OWN:
        return {"kind": kind, "source_type": ""}

    st.caption("Источник будет связан с рабочими наборами после безопасного импорта; химические значения от этого не меняются.")
    c1, c2 = st.columns(2)
    title = c1.text_input(
        "Название работы / набора",
        value=Path(filename).stem,
        key=f"universal_source_title_{token}",
    )
    citation = c2.text_input(
        "Короткая ссылка",
        placeholder="Reguir et al., 2009",
        key=f"universal_source_citation_{token}",
    )
    c3, c4 = st.columns(2)
    doi = c3.text_input("DOI", key=f"universal_source_doi_{token}")
    colleague = ""
    if kind == _SOURCE_COLLEAGUE:
        colleague = c4.text_input("От кого получены данные", key=f"universal_source_colleague_{token}")
    else:
        authors = c4.text_input("Авторы", key=f"universal_source_authors_{token}")
    with st.expander("Дополнительная библиография", expanded=False):
        if kind == _SOURCE_COLLEAGUE:
            authors = st.text_input("Авторы / участники", key=f"universal_source_authors_{token}")
        year = st.text_input("Год", key=f"universal_source_year_{token}")
        journal = st.text_input("Журнал / организация", key=f"universal_source_journal_{token}")
        notes = st.text_area("Заметка", key=f"universal_source_notes_{token}")
    return {
        "kind": kind,
        "source_type": _SOURCE_TYPES[kind],
        "title": title,
        "citation": citation,
        "doi": doi,
        "authors": authors,
        "year": year,
        "journal": journal,
        "colleague": colleague,
        "notes": notes,
    }


def _ensure_study(project_id: int, token: str, details: dict) -> int | None:
    if not details.get("source_type"):
        return None
    key = f"universal_study_id_{token}"
    stored = st.session_state.get(key)
    if stored is not None:
        return int(stored)
    study_id = create_study(
        int(project_id),
        source_type=str(details["source_type"]),
        title=str(details.get("title") or ""),
        citation=str(details.get("citation") or ""),
        doi=str(details.get("doi") or ""),
        authors=str(details.get("authors") or ""),
        year=str(details.get("year") or ""),
        journal=str(details.get("journal") or ""),
        colleague=str(details.get("colleague") or ""),
        notes=str(details.get("notes") or ""),
    )
    st.session_state[key] = int(study_id)
    return int(study_id)


def render_table_import_with_provenance(
    original: Callable,
    project_id: int,
    name: str,
    data: bytes,
    token: str,
) -> list[int]:
    """Wrap the safe table import and attach explicit source provenance afterwards."""
    details = _source_controls(token, name)
    working = [int(value) for value in original(project_id, name, data, token)]
    if not working or not details.get("source_type"):
        return working
    try:
        study_id = _ensure_study(int(project_id), token, details)
        if study_id is not None:
            for dataset_id in working:
                link_dataset_to_study(int(dataset_id), int(study_id))
    except Exception as exc:
        st.error(f"Данные импортированы, но provenance источника не удалось связать: {exc}")
    else:
        st.caption("Источник таблицы сохранён и связан с рабочими наборами.")
    return working


def _batch_token(image_files: list[tuple[str, bytes]]) -> str:
    payload = "|".join(
        f"{name}:{hashlib.sha256(raw).hexdigest()}" for name, raw in image_files
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def _group_assignments_by_dataset(
    items: list[tuple[int, ImageAssignment]],
) -> dict[int, list[ImageAssignment]]:
    grouped: dict[int, list[ImageAssignment]] = defaultdict(list)
    for dataset_id, assignment in items:
        grouped[int(dataset_id)].append(assignment)
    return dict(grouped)


def _reset_scope_after_dataset_change(prefix: str, dataset_id: int) -> None:
    marker = f"{prefix}_last_dataset_id"
    previous = st.session_state.get(marker)
    if previous is not None and int(previous) != int(dataset_id):
        for suffix in (
            "_analysis_ids", "_point_query", "_field_column", "_field_value",
        ):
            st.session_state.pop(f"{prefix}{suffix}", None)
    st.session_state[marker] = int(dataset_id)


def _cleanup_cross_dataset_batch(asset_ids: list[int]) -> list[str]:
    errors: list[str] = []
    for asset_id in reversed(asset_ids):
        try:
            delete_image_asset(int(asset_id))
        except Exception as exc:
            errors.append(f"asset {asset_id}: {exc}")
    return errors


def render_image_wizard_multi_dataset(
    project_id: int,
    image_files: list[tuple[str, bytes]],
    preferred_dataset_ids: list[int],
) -> None:
    """Walk images one-by-one; dataset and point scope are chosen per image."""
    if not image_files:
        return
    render_section_header(
        "2. Фотографии и карты",
        "Каждый файл отдельно: какой dataset и какие именно точки на нём видны",
    )
    datasets = list_accessible_datasets(int(project_id))
    if not datasets:
        st.info("Сначала импортируйте таблицу анализов.")
        return
    by_id = {int(item["id"]): item for item in datasets}
    dataset_options = list(by_id)
    preferred = next(
        (int(value) for value in preferred_dataset_ids if int(value) in by_id),
        dataset_options[0],
    )

    batch = _batch_token(image_files)
    index_key = f"univimg_index_{batch}"
    index = min(int(st.session_state.get(index_key, 0)), len(image_files) - 1)
    st.session_state[index_key] = index
    name, raw = image_files[index]
    token = base._file_token(name, raw)
    prefix = f"univimg_{batch}_{token}"
    dataset_key = f"{prefix}_dataset_id"
    if st.session_state.get(dataset_key) not in by_id:
        st.session_state[dataset_key] = preferred

    statuses = []
    for i, (item_name, item_raw) in enumerate(image_files):
        item_prefix = f"univimg_{batch}_{base._file_token(item_name, item_raw)}"
        item_dataset = st.session_state.get(f"{item_prefix}_dataset_id")
        scope_label = st.session_state.get(f"{item_prefix}_scope", "К нескольким точкам анализа")
        scope_type = SCOPE_LABELS[scope_label]
        ready = (
            scope_type == "skip"
            or (item_dataset in by_id and assignment_error(item_prefix, scope_type) is None)
        )
        marker = "→" if i == index else ("✓" if ready else "○")
        statuses.append((
            f"{marker} {item_name}",
            "accent" if i == index else "success" if ready else "neutral",
        ))
    render_badges(statuses[:12])
    if len(statuses) > 12:
        st.caption(f"Ещё файлов: {len(statuses) - 12}")
    st.progress((index + 1) / len(image_files), text=f"{index + 1} из {len(image_files)} · {name}")

    left, right = st.columns([1.3, 1])
    with left:
        try:
            st.image(raw, caption=name, width="stretch")
        except Exception:
            st.info("Предпросмотр недоступен, но файл можно проверить и сохранить.")
    with right:
        dataset_id = st.selectbox(
            "К какому набору относятся точки на этом изображении",
            dataset_options,
            format_func=lambda value: (
                f"{by_id[int(value)]['name']} · {int(by_id[int(value)].get('row_count') or 0)} строк"
            ),
            key=dataset_key,
        )
        _reset_scope_after_dataset_change(prefix, int(dataset_id))
        dataframe = load_dataset_dataframe(int(dataset_id), include_meta=True)
        st.selectbox("Тип", IMAGE_KINDS, key=f"{prefix}_kind")
        st.text_input("Подпись", value=Path(name).stem, key=f"{prefix}_title")
        scope_label = st.radio("Связать с", list(SCOPE_LABELS), key=f"{prefix}_scope")
        scope_type = SCOPE_LABELS[scope_label]
        if scope_type == SCOPE_ANALYSIS:
            render_multi_point_controls(prefix, dataframe)
        elif scope_type == SCOPE_FIELD:
            render_field_controls(prefix, dataframe)
        elif scope_type == SCOPE_DATASET:
            st.caption("Изображение относится ко всему выбранному набору.")
        else:
            st.caption("Этот файл будет пропущен.")

    back, next_col, save = st.columns([1, 1, 2])
    if back.button("← Назад", disabled=index == 0, width="stretch", key=f"univimg_back_{batch}"):
        st.session_state[index_key] = index - 1
        st.rerun()
    if next_col.button("Далее →", disabled=index == len(image_files) - 1, width="stretch", key=f"univimg_next_{batch}"):
        error = assignment_error(prefix, scope_type)
        if error:
            st.error(error)
        else:
            st.session_state[index_key] = index + 1
            st.rerun()

    prepared: list[tuple[int, ImageAssignment]] = []
    errors: list[str] = []
    for item_name, item_raw in image_files:
        item_prefix = f"univimg_{batch}_{base._file_token(item_name, item_raw)}"
        item_scope_label = st.session_state.get(f"{item_prefix}_scope", "К нескольким точкам анализа")
        if SCOPE_LABELS[item_scope_label] == "skip":
            continue
        item_dataset = st.session_state.get(f"{item_prefix}_dataset_id")
        if item_dataset not in by_id:
            errors.append(item_name)
            continue
        try:
            assignment = base._image_assignment(item_prefix, item_name, item_raw)
        except ValueError:
            errors.append(item_name)
            continue
        if assignment is not None:
            prepared.append((int(item_dataset), assignment))

    if save.button("Проверить и сохранить всю пачку", type="primary", width="stretch", key=f"univimg_save_{batch}"):
        if errors:
            st.warning("Не закончена настройка: " + ", ".join(errors[:8]))
            return
        if not prepared:
            st.warning("Нет изображений для сохранения.")
            return
        grouped = _group_assignments_by_dataset(prepared)
        created_ids: list[int] = []
        try:
            for dataset_id, assignments in grouped.items():
                result = create_assigned_image_batch(
                    project_id=int(project_id),
                    dataset_id=int(dataset_id),
                    assignments=assignments,
                )
                created_ids.extend(int(value) for value in result.asset_ids)
        except Exception as exc:
            cleanup_errors = _cleanup_cross_dataset_batch(created_ids)
            st.error(f"Пачка не сохранена: {exc}")
            if cleanup_errors:
                st.error("Не удалось полностью откатить уже созданные изображения: " + " · ".join(cleanup_errors[:5]))
        else:
            st.success(
                f"Сохранено изображений: {len(created_ids)} · наборов: {len(grouped)}."
            )
            base._clear_image_state(batch)
            st.rerun()
