"""Universal drop-zone for a common PetroLab intake sequence: table first, images next."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.auto_pipeline import auto_process_imported_datasets
from petrolab.column_schema import CANONICAL_ROLES
from petrolab.db import get_or_create_library_project, link_dataset_to_project, list_accessible_datasets, load_dataset_dataframe
from petrolab.services.image_service import (
    ImageAssignment,
    ImagePayload,
    ImageScope,
    SCOPE_ANALYSIS,
    SCOPE_DATASET,
    SCOPE_FIELD,
    create_assigned_image_batch,
)
from petrolab.services.import_service import (
    ImportSchemaPreview,
    import_uploaded_sheets,
    inspect_uploaded_sheet,
    list_uploaded_sheets,
    preview_uploaded_source,
)
from petrolab.ui.image_components import (
    IMAGE_KINDS,
    SCOPE_LABELS,
    assignment_error,
    render_field_controls,
    render_multi_point_controls,
)
from petrolab.ui.layout import render_badges, render_hint, render_section_header


_TABLE_SUFFIXES = {".xlsx", ".xlsm", ".xls", ".csv"}
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}
_KIND_TABLE = "Аналитическая таблица"
_KIND_IMAGE = "Изображение / карта / фотография"
_KIND_SKIP = "Не добавлять"

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


def _guessed_kind(filename: str) -> str:
    suffix = Path(str(filename)).suffix.lower()
    if suffix in _TABLE_SUFFIXES:
        return _KIND_TABLE
    if suffix in _IMAGE_SUFFIXES:
        return _KIND_IMAGE
    return _KIND_SKIP


def _file_token(name: str, data: bytes) -> str:
    return hashlib.sha256(str(name).encode("utf-8") + b"\0" + data).hexdigest()[:16]


def _safe_semantic_mapping(preview: ImportSchemaPreview, sheet: str, token: str) -> tuple[dict[str, str], list[str]]:
    blockers: list[str] = []
    if preview.duplicate_canonical_columns:
        blockers.append(
            "Есть несколько физических колонок, нормализованных в один химический компонент: "
            + ", ".join(preview.duplicate_canonical_columns)
        )
    if not preview.recognized_oxides and not preview.recognized_traces:
        blockers.append("Не распознано ни одной химической колонки.")

    suggestions = dict(preview.schema.suggested or {})
    semantic: dict[str, str] = {}
    for role in CANONICAL_ROLES:
        suggested = suggestions.get(role)
        if suggested:
            semantic[str(role)] = str(suggested)
            continue
        weak = tuple((preview.schema.weak_candidates or {}).get(role, ()))
        if not weak:
            continue
        choice = st.selectbox(
            f"{sheet or 'CSV'} · что является «{role}»?",
            ["— не назначать —", *[str(value) for value in weak]],
            key=f"universal_semantic_{token}_{sheet}_{role}",
            help="PetroLab не выбирает между неоднозначными идентификаторами молча.",
        )
        if choice != "— не назначать —":
            semantic[str(role)] = str(choice)
    return semantic, blockers


def _iron_semantics(previews: dict[str, ImportSchemaPreview], token: str) -> tuple[dict[str, dict[str, str]], bool]:
    maps: dict[str, dict[str, str]] = {}
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
                key=f"universal_iron_{token}_{sheet}_{iron}",
            )
            if choice is None:
                ready = False
            else:
                mapping[iron] = choices[choice]
        maps[sheet] = mapping
    return maps, ready


def _imported_state_key(token: str) -> str:
    return f"universal_imported_{token}"


def _render_table_import(project_id: int, name: str, data: bytes, token: str) -> list[int]:
    stored = [int(value) for value in st.session_state.get(_imported_state_key(token), [])]
    if stored:
        st.success(f"Таблица уже импортирована в этой сессии. Рабочих наборов: {len(stored)}.")
        return stored

    render_section_header("1. Аналитическая таблица", "Проверка схемы до любой записи")
    header_row = int(st.number_input(
        "Строка заголовков",
        min_value=1,
        max_value=200,
        value=1,
        step=1,
        key=f"universal_header_{token}",
    ))
    try:
        sheets = list_uploaded_sheets(data, name)
    except Exception as exc:
        st.error(f"Файл не удалось открыть как таблицу: {exc}")
        return []
    selected = st.multiselect(
        "Листы",
        sheets,
        default=sheets[:1],
        key=f"universal_sheets_{token}",
    )
    if not selected:
        st.info("Выберите хотя бы один лист.")
        return []

    dataset_name = st.text_input(
        "Название набора",
        value=Path(name).stem,
        key=f"universal_dataset_name_{token}",
    )
    previews: dict[str, ImportSchemaPreview] = {}
    semantic_maps: dict[str, dict[str, str]] = {}
    blockers: list[str] = []
    preview_rows: list[dict] = []
    for sheet in selected:
        try:
            preview = inspect_uploaded_sheet(data, name, sheet, header_row)
        except Exception as exc:
            blockers.append(f"{sheet or 'CSV'}: {exc}")
            continue
        previews[sheet] = preview
        semantic, hard = _safe_semantic_mapping(preview, sheet, token)
        semantic_maps[sheet] = semantic
        blockers.extend(f"{sheet or 'CSV'}: {item}" for item in hard)
        preview_rows.append({
            "Лист": sheet or "CSV",
            "Строк": int(preview.row_count),
            "Оксидов": len(preview.recognized_oxides),
            "Trace": len(preview.recognized_traces),
            "<DL / <LOD": int(preview.detection_limit_cells),
            "Формат": preview.adapter_name or "обычная таблица",
        })
    if preview_rows:
        st.dataframe(pd.DataFrame(preview_rows), width="stretch", hide_index=True)
    if blockers:
        st.error("Автоматически продолжать небезопасно: " + " · ".join(blockers[:8]))
        st.caption("Для конфликтующих химических колонок используйте расширенный импорт «Новые анализы»; файл здесь не записан.")
        return []

    measurement_maps, iron_ready = _iron_semantics(previews, token)
    if not iron_ready:
        st.info("Нужно ответить только на неоднозначный вопрос о железе.")
        return []

    normalized: dict[str, pd.DataFrame] = {}
    try:
        for sheet in selected:
            normalized[sheet] = preview_uploaded_source(
                data,
                name,
                sheet,
                header_row,
                "generic",
                semantic_maps.get(sheet, {}),
                measurement_maps.get(sheet, {}),
            )
    except Exception as exc:
        st.error(f"Preflight не пройден: {exc}")
        return []
    with st.expander("Предпросмотр нормализованных данных", expanded=False):
        for sheet, frame in normalized.items():
            st.caption(sheet or "CSV")
            st.dataframe(frame.head(30), width="stretch", hide_index=True)

    if st.button(
        "Импортировать таблицу",
        type="primary",
        width="stretch",
        key=f"universal_import_table_{token}",
    ):
        try:
            imported = import_uploaded_sheets(
                project_id=get_or_create_library_project(),
                file_bytes=data,
                filename=name,
                sheet_names=selected,
                mineral_key="generic",
                dataset_name=dataset_name,
                header_row=header_row,
                semantic_maps=semantic_maps,
                measurement_maps=measurement_maps,
                header_rows={sheet: header_row for sheet in selected},
                mineral_keys={sheet: "generic" for sheet in selected},
            )
            for dataset_id in imported.dataset_ids:
                link_dataset_to_project(
                    int(project_id), int(dataset_id),
                    "Добавлено через универсальный +",
                    purpose="working",
                )
            report = auto_process_imported_datasets(int(project_id), list(imported.dataset_ids))
            working = list(report.working_dataset_ids) or [int(value) for value in imported.dataset_ids]
            st.session_state[_imported_state_key(token)] = working
            st.session_state["workflow_recent_dataset_ids"] = working
            st.session_state["workflow_recent_import_target"] = int(project_id)
        except Exception as exc:
            st.error(f"Импорт остановлен: {exc}")
        else:
            st.success("Таблица импортирована. Теперь можно сразу привязать фотографии ниже.")
            st.rerun()
    return []


def _image_assignment(prefix: str, filename: str, data: bytes) -> ImageAssignment | None:
    scope_label = st.session_state.get(f"{prefix}_scope", "К нескольким точкам анализа")
    scope_type = SCOPE_LABELS[scope_label]
    if scope_type == "skip":
        return None
    error = assignment_error(prefix, scope_type)
    if error:
        raise ValueError(error)
    if scope_type == SCOPE_ANALYSIS:
        scope = ImageScope(
            SCOPE_ANALYSIS,
            analysis_ids=tuple(st.session_state.get(f"{prefix}_analysis_ids", [])),
        )
    elif scope_type == SCOPE_FIELD:
        scope = ImageScope(
            SCOPE_FIELD,
            scope_column=str(st.session_state.get(f"{prefix}_field_column", "")),
            scope_value=str(st.session_state.get(f"{prefix}_field_value", "")),
        )
    else:
        scope = ImageScope(SCOPE_DATASET)
    return ImageAssignment(
        ImagePayload(filename, data),
        scope,
        str(st.session_state.get(f"{prefix}_kind", IMAGE_KINDS[0])),
        str(st.session_state.get(f"{prefix}_title", Path(filename).stem)),
    )


def _clear_image_state(batch_token: str) -> None:
    prefix = f"univimg_{batch_token}_"
    for key in list(st.session_state):
        if str(key).startswith(prefix) or key == f"univimg_index_{batch_token}":
            del st.session_state[key]


def _render_image_wizard(project_id: int, image_files: list[tuple[str, bytes]], preferred_dataset_ids: list[int]) -> None:
    if not image_files:
        return
    render_section_header("2. Фотографии и карты", "По одному файлу: к каким именно точкам его привязать")
    datasets = list_accessible_datasets(project_id)
    if not datasets:
        st.info("Сначала импортируйте таблицу анализов.")
        return
    by_id = {int(item["id"]): item for item in datasets}
    options = list(by_id)
    preferred = next((value for value in preferred_dataset_ids if value in by_id), options[0])
    dataset_id = st.selectbox(
        "Набор анализов для этой пачки фотографий",
        options,
        index=options.index(preferred),
        format_func=lambda value: f"{by_id[int(value)]['name']} · {by_id[int(value)].get('row_count', 0)} строк",
        key="universal_image_dataset",
    )
    dataframe = load_dataset_dataframe(int(dataset_id), include_meta=True)
    batch_hash = hashlib.sha256(
        "|".join(f"{name}:{hashlib.sha256(raw).hexdigest()}" for name, raw in image_files).encode("utf-8")
    ).hexdigest()[:12]
    batch_token = f"{int(dataset_id)}_{batch_hash}"
    index_key = f"univimg_index_{batch_token}"
    index = min(int(st.session_state.get(index_key, 0)), len(image_files) - 1)
    st.session_state[index_key] = index
    name, raw = image_files[index]
    token = _file_token(name, raw)
    prefix = f"univimg_{batch_token}_{token}"

    statuses = []
    for i, (item_name, item_raw) in enumerate(image_files):
        item_prefix = f"univimg_{batch_token}_{_file_token(item_name, item_raw)}"
        scope_label = st.session_state.get(f"{item_prefix}_scope", "К нескольким точкам анализа")
        scope_type = SCOPE_LABELS[scope_label]
        ready = assignment_error(item_prefix, scope_type) is None
        marker = "→" if i == index else ("✓" if ready else "○")
        statuses.append((f"{marker} {item_name}", "accent" if i == index else "success" if ready else "neutral"))
    render_badges(statuses[:12])
    st.progress((index + 1) / len(image_files), text=f"{index + 1} из {len(image_files)} · {name}")

    left, right = st.columns([1.3, 1])
    with left:
        try:
            st.image(raw, caption=name, width="stretch")
        except Exception:
            st.info("Предпросмотр недоступен, но файл можно проверить и сохранить.")
    with right:
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
    if back.button("← Назад", disabled=index == 0, width="stretch", key=f"univimg_back_{batch_token}"):
        st.session_state[index_key] = index - 1
        st.rerun()
    if next_col.button("Далее →", disabled=index == len(image_files) - 1, width="stretch", key=f"univimg_next_{batch_token}"):
        error = assignment_error(prefix, scope_type)
        if error:
            st.error(error)
        else:
            st.session_state[index_key] = index + 1
            st.rerun()

    assignments: list[ImageAssignment] = []
    errors: list[str] = []
    for item_name, item_raw in image_files:
        item_prefix = f"univimg_{batch_token}_{_file_token(item_name, item_raw)}"
        try:
            assignment = _image_assignment(item_prefix, item_name, item_raw)
            if assignment is not None:
                assignments.append(assignment)
        except ValueError:
            errors.append(item_name)
    if save.button("Проверить и сохранить всю пачку", type="primary", width="stretch", key=f"univimg_save_{batch_token}"):
        if errors:
            st.warning("Не закончена настройка: " + ", ".join(errors[:8]))
        elif not assignments:
            st.warning("Нет изображений для сохранения.")
        else:
            try:
                result = create_assigned_image_batch(
                    project_id=project_id,
                    dataset_id=int(dataset_id),
                    assignments=assignments,
                )
            except Exception as exc:
                st.error(f"Пачка не сохранена: {exc}")
            else:
                st.success(f"Сохранено изображений: {result.count}.")
                _clear_image_state(batch_token)
                st.rerun()


def render_universal_intake(project_id: int) -> None:
    st.divider()
    render_section_header(
        "Универсальный +",
        "Перетащите Excel/CSV и/или фотографии. PetroLab сначала показывает, чем считает каждый файл, и ничего не записывает до проверки.",
    )
    uploads = st.file_uploader(
        "Файлы",
        type=["xlsx", "xlsm", "xls", "csv", "png", "jpg", "jpeg", "webp", "tif", "tiff"],
        accept_multiple_files=True,
        key="universal_intake_files",
    )
    if not uploads:
        render_hint("Типичный сценарий: бросить Excel и десять фотографий → импортировать таблицу → пройти фотографии одну за другой и указать связанные точки.")
        return

    classified: list[tuple[str, bytes, str]] = []
    for index, upload in enumerate(uploads):
        data = upload.getvalue()
        guessed = _guessed_kind(upload.name)
        kind = st.selectbox(
            upload.name,
            [_KIND_TABLE, _KIND_IMAGE, _KIND_SKIP],
            index=[_KIND_TABLE, _KIND_IMAGE, _KIND_SKIP].index(guessed),
            key=f"universal_kind_{index}_{_file_token(upload.name, data)}",
            help="Это явное подтверждение типа файла; расширение используется только как подсказка.",
        )
        classified.append((upload.name, data, kind))

    tables = [(name, data) for name, data, kind in classified if kind == _KIND_TABLE]
    images = [(name, data) for name, data, kind in classified if kind == _KIND_IMAGE]
    render_badges([
        (f"таблиц · {len(tables)}", "accent" if tables else "neutral"),
        (f"изображений · {len(images)}", "accent" if images else "neutral"),
    ])
    if len(tables) > 1:
        st.warning("В одной универсальной пачке сейчас обрабатывается одна аналитическая таблица. Оставьте остальные как «Не добавлять» и загрузите следующей пачкой.")
        return

    preferred_ids: list[int] = []
    if tables:
        name, data = tables[0]
        token = _file_token(name, data)
        preferred_ids = _render_table_import(project_id, name, data, token)
        if not preferred_ids:
            # Images remain visible in the uploader but are intentionally not stored before
            # the analytical table has a safe target context.
            if images:
                st.info("Фотографии будут доступны для привязки сразу после безопасного импорта таблицы.")
            return
    _render_image_wizard(project_id, images, preferred_ids)
