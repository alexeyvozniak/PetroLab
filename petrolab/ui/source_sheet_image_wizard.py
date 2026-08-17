from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.services.image_service import (
    ImageAssignment,
    ImagePayload,
    ImageScope,
    SCOPE_ANALYSIS,
    SCOPE_DATASET,
    SCOPE_FIELD,
    delete_image_asset,
    image_preview_bytes,
)
from petrolab.services.source_sheet_image_service import create_source_sheet_image_batch
from petrolab.source_sheet_scope import (
    CONFIRMED_PHASE_COLUMN,
    SourceSheetScope,
    list_source_sheet_scopes,
    load_source_sheet_universe,
)
from petrolab.ui import universal_intake as base
from petrolab.ui.image_components import IMAGE_KINDS, SCOPE_LABELS, analysis_id_labels
from petrolab.ui.layout import render_badges, render_section_header


def _sheet_token(scope: SourceSheetScope) -> str:
    return hashlib.sha256(scope.key.encode("utf-8")).hexdigest()[:10]


def _draft_prefix(batch: str, filename: str, raw: bytes, scope: SourceSheetScope) -> str:
    image_token = base._file_token(filename, raw)
    return f"univimg_{batch}_{image_token}_sheet_{_sheet_token(scope)}"


def _active_sheet_key(batch: str, filename: str, raw: bytes) -> str:
    return f"univimg_{batch}_{base._file_token(filename, raw)}_source_sheet"


def _batch_token(image_files: list[tuple[str, bytes]]) -> str:
    payload = "|".join(
        f"{name}:{hashlib.sha256(raw).hexdigest()}" for name, raw in image_files
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:12]


def _point_label(row: pd.Series, fallback: str) -> str:
    point = str(row.get("Point") or "").strip()
    sample = str(row.get("Sample") or "").strip()
    phase = str(row.get(CONFIRMED_PHASE_COLUMN) or "").strip()
    source_row = row.get("_source_row", "—")
    pieces = [value for value in (sample, point) if value]
    identity = " · ".join(pieces) or fallback[:8]
    if phase:
        identity += f" · {phase}"
    return f"{identity} · Excel {source_row}"


def _render_point_controls(prefix: str, dataframe: pd.DataFrame) -> None:
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        st.info("В этом исходном листе нет аналитических точек.")
        return
    query = st.text_input(
        "Найти точку",
        key=f"{prefix}_point_query",
        placeholder="Sample, Point или фаза — например 19, P-14, magnetite",
    )
    filtered = dataframe
    needle = str(query or "").strip().casefold()
    if needle:
        columns = [
            column for column in ("Sample", "Grain", "Point", CONFIRMED_PHASE_COLUMN, "Mineral", "Минерал")
            if column in dataframe.columns
        ]
        mask = pd.Series(False, index=dataframe.index, dtype=bool)
        for column in columns:
            mask |= dataframe[column].astype(str).str.casefold().str.contains(needle, na=False, regex=False)
        filtered = dataframe.loc[mask].copy()

    labels = analysis_id_labels(dataframe)
    if CONFIRMED_PHASE_COLUMN in dataframe.columns:
        by_id = dataframe.set_index("_analysis_id", drop=False)
        for analysis_id in list(labels):
            if analysis_id in by_id.index:
                row = by_id.loc[analysis_id]
                if isinstance(row, pd.DataFrame):
                    row = row.iloc[0]
                labels[analysis_id] = _point_label(row, analysis_id)

    selected_key = f"{prefix}_analysis_ids"
    previous = [str(value) for value in st.session_state.get(selected_key, [])]
    all_ids = set(dataframe["_analysis_id"].astype(str))
    valid_previous = [value for value in previous if value in all_ids]
    option_ids = list(dict.fromkeys(valid_previous + filtered["_analysis_id"].astype(str).head(5000).tolist()))
    if selected_key not in st.session_state or previous != valid_previous:
        st.session_state[selected_key] = valid_previous
    st.multiselect(
        "Какие точки видны на фотографии?",
        option_ids,
        format_func=lambda analysis_id: labels.get(str(analysis_id), str(analysis_id)[:8]),
        key=selected_key,
    )
    st.caption(
        f"Весь лист: {len(dataframe)} анализов · найдено: {len(filtered)} · выбрано: {len(st.session_state.get(selected_key, []))}."
    )


def _render_field_controls(prefix: str, dataframe: pd.DataFrame) -> None:
    candidates = [
        column for column in ("Sample", "Grain", "Generation", "Point", CONFIRMED_PHASE_COLUMN)
        if column in dataframe.columns and dataframe[column].notna().any()
    ]
    if not candidates:
        st.warning("Для групповой привязки нет подходящего поля. Выберите конкретные аналитические точки.")
        return
    column = st.selectbox("Поле", candidates, key=f"{prefix}_field_column")
    values = sorted(dataframe[column].dropna().astype(str).unique().tolist())
    if values:
        st.selectbox("Значение", values, key=f"{prefix}_field_value")


def _assignment_from_draft(prefix: str, filename: str, raw: bytes) -> ImageAssignment | None:
    scope_label = st.session_state.get(f"{prefix}_scope", "К нескольким точкам анализа")
    scope_type = SCOPE_LABELS[scope_label]
    if scope_type == "skip":
        return None
    if scope_type == SCOPE_ANALYSIS:
        ids = tuple(str(value) for value in st.session_state.get(f"{prefix}_analysis_ids", []) if str(value))
        if not ids:
            raise ValueError("Не выбрана ни одна аналитическая точка")
        scope = ImageScope(SCOPE_ANALYSIS, analysis_ids=ids)
    elif scope_type == SCOPE_FIELD:
        column = str(st.session_state.get(f"{prefix}_field_column") or "").strip()
        value = str(st.session_state.get(f"{prefix}_field_value") or "").strip()
        if not column or not value:
            raise ValueError("Не выбрано поле/значение")
        dataframe = st.session_state.get(f"{prefix}_source_sheet_frame")
        if not isinstance(dataframe, pd.DataFrame) or column not in dataframe.columns:
            raise ValueError("Не удалось восстановить исходный лист для групповой привязки")
        ids = tuple(
            dataframe.loc[dataframe[column].astype(str) == value, "_analysis_id"].astype(str).tolist()
        )
        if not ids:
            raise ValueError("В выбранной группе нет аналитических точек")
        scope = ImageScope(SCOPE_ANALYSIS, analysis_ids=ids)
    elif scope_type == SCOPE_DATASET:
        dataframe = st.session_state.get(f"{prefix}_source_sheet_frame")
        if not isinstance(dataframe, pd.DataFrame) or "_analysis_id" not in dataframe.columns:
            raise ValueError("Не удалось восстановить исходный лист")
        ids = tuple(dataframe["_analysis_id"].astype(str).tolist())
        scope = ImageScope(SCOPE_ANALYSIS, analysis_ids=ids)
    else:
        raise ValueError("Неизвестный тип привязки")
    return ImageAssignment(
        ImagePayload(filename, raw),
        scope,
        str(st.session_state.get(f"{prefix}_kind", IMAGE_KINDS[0])),
        str(st.session_state.get(f"{prefix}_title", Path(filename).stem)),
    )


def _draft_ready(prefix: str) -> bool:
    scope_label = st.session_state.get(f"{prefix}_scope", "К нескольким точкам анализа")
    scope_type = SCOPE_LABELS[scope_label]
    if scope_type == "skip":
        return True
    if scope_type == SCOPE_ANALYSIS:
        return bool(st.session_state.get(f"{prefix}_analysis_ids"))
    if scope_type == SCOPE_FIELD:
        return bool(st.session_state.get(f"{prefix}_field_column")) and bool(st.session_state.get(f"{prefix}_field_value"))
    if scope_type == SCOPE_DATASET:
        return True
    return False


def _cleanup_cross_sheet_batch(asset_ids: list[int]) -> list[str]:
    errors: list[str] = []
    for asset_id in reversed(asset_ids):
        try:
            delete_image_asset(int(asset_id))
        except Exception as exc:
            errors.append(f"asset {asset_id}: {exc}")
    return errors


def _prepare_batch(
    image_files: list[tuple[str, bytes]],
    *,
    batch: str,
    by_key: dict[str, SourceSheetScope],
    preferred_scope: SourceSheetScope,
) -> tuple[list[tuple[SourceSheetScope, ImageAssignment]], list[str]]:
    prepared: list[tuple[SourceSheetScope, ImageAssignment]] = []
    errors: list[str] = []
    for item_name, item_raw in image_files:
        item_active = st.session_state.get(_active_sheet_key(batch, item_name, item_raw), preferred_scope.key)
        item_scope = by_key.get(str(item_active), preferred_scope)
        item_prefix = _draft_prefix(batch, item_name, item_raw, item_scope)
        try:
            assignment = _assignment_from_draft(item_prefix, item_name, item_raw)
        except ValueError:
            errors.append(item_name)
            continue
        if assignment is not None:
            prepared.append((item_scope, assignment))
    return prepared, errors


def _save_prepared_batch(
    project_id: int,
    prepared: list[tuple[SourceSheetScope, ImageAssignment]],
) -> tuple[list[int], list[str]]:
    created: list[int] = []
    try:
        for scope, assignment in prepared:
            result = create_source_sheet_image_batch(
                project_id=int(project_id),
                anchor_dataset_id=int(scope.anchor_dataset_id),
                assignments=[assignment],
            )
            created.extend(int(value) for value in result.asset_ids)
    except Exception as exc:
        cleanup_errors = _cleanup_cross_sheet_batch(created)
        errors = [f"Пачка не сохранена: {exc}"]
        if cleanup_errors:
            errors.append("Не удалось полностью откатить уже созданные изображения: " + " · ".join(cleanup_errors[:5]))
        return [], errors
    return created, []


def render_source_sheet_image_wizard(
    project_id: int,
    image_files: list[tuple[str, bytes]],
    preferred_dataset_ids: list[int],
) -> None:
    """Simple sequential image linker over the immutable source-sheet universe."""
    if not image_files:
        return
    scopes = list_source_sheet_scopes(int(project_id))
    if not scopes:
        st.info("Сначала импортируйте аналитическую таблицу. После этого все её исходные листы появятся здесь.")
        return
    by_key = {scope.key: scope for scope in scopes}
    preferred_scope = next(
        (
            scope for scope in scopes
            if any(int(dataset_id) in scope.dataset_ids for dataset_id in preferred_dataset_ids)
        ),
        scopes[0],
    )

    render_section_header(
        "Изображения",
        "Для каждой фотографии выберите исходный лист и точки. Минералогическое разбиение наборов не скрывает точки листа.",
    )
    st.caption(
        "Черновик хранится отдельно для каждой фотографии и каждого листа. Можно переключаться между листами и возвращаться назад — выбор не стирается."
    )

    batch = _batch_token(image_files)
    index_key = f"univimg_index_{batch}"
    index = min(int(st.session_state.get(index_key, 0)), len(image_files) - 1)
    st.session_state[index_key] = index
    name, raw = image_files[index]
    active_key = _active_sheet_key(batch, name, raw)
    if st.session_state.get(active_key) not in by_key:
        st.session_state[active_key] = preferred_scope.key

    statuses = []
    for i, (item_name, item_raw) in enumerate(image_files):
        item_active = st.session_state.get(_active_sheet_key(batch, item_name, item_raw), preferred_scope.key)
        item_scope = by_key.get(str(item_active), preferred_scope)
        item_prefix = _draft_prefix(batch, item_name, item_raw, item_scope)
        ready = _draft_ready(item_prefix)
        marker = "→" if i == index else ("✓" if ready else "○")
        statuses.append((f"{marker} {item_name}", "accent" if i == index else "success" if ready else "neutral"))
    render_badges(statuses[:12])
    if len(statuses) > 12:
        st.caption(f"Ещё файлов: {len(statuses) - 12}")
    st.progress((index + 1) / len(image_files), text=f"Фото {index + 1} из {len(image_files)} · {name}")

    left, right = st.columns([1.25, 1])
    with left:
        try:
            st.image(image_preview_bytes(ImagePayload(name, raw)), caption=name, width="stretch")
        except Exception:
            st.info("Предпросмотр недоступен, но файл можно сохранить.")
    with right:
        st.markdown("#### К чему относится это изображение?")
        selected_sheet_key = st.selectbox(
            "Исходный лист",
            list(by_key),
            format_func=lambda key: by_key[str(key)].label,
            key=active_key,
            help="Показывается полный исходный лист аналитической сессии, а не отдельный фазовый набор.",
        )
        scope = by_key[str(selected_sheet_key)]
        prefix = _draft_prefix(batch, name, raw, scope)
        dataframe = load_source_sheet_universe(int(project_id), scope)
        st.session_state[f"{prefix}_source_sheet_frame"] = dataframe
        st.session_state.setdefault(f"{prefix}_scope", "К нескольким точкам анализа")

        scope_label = str(st.session_state.get(f"{prefix}_scope") or "К нескольким точкам анализа")
        scope_type = SCOPE_LABELS.get(scope_label, SCOPE_ANALYSIS)
        if scope_type == SCOPE_ANALYSIS:
            _render_point_controls(prefix, dataframe)
        elif scope_type == SCOPE_FIELD:
            _render_field_controls(prefix, dataframe)
        elif scope_type == SCOPE_DATASET:
            st.info(f"Будут связаны все {len(dataframe)} анализов исходного листа.")
        else:
            st.info("Эта фотография будет пропущена.")

        with st.expander("Дополнительно", expanded=False):
            st.selectbox("Тип изображения", IMAGE_KINDS, key=f"{prefix}_kind")
            st.text_input("Подпись", value=Path(name).stem, key=f"{prefix}_title")
            st.selectbox(
                "Другой способ привязки",
                list(SCOPE_LABELS),
                key=f"{prefix}_scope",
                help="Обычно ничего менять не нужно: выбирайте конкретные точки выше.",
            )

    prepared, errors = _prepare_batch(
        image_files,
        batch=batch,
        by_key=by_key,
        preferred_scope=preferred_scope,
    )

    back, action = st.columns([1, 2.2])
    if back.button("← Предыдущее фото", disabled=index == 0, width="stretch", key=f"univimg_back_{batch}"):
        st.session_state[index_key] = index - 1
        st.rerun()

    if index < len(image_files) - 1:
        if action.button(
            "Готово → следующая фотография",
            type="primary",
            width="stretch",
            key=f"univimg_next_{batch}",
        ):
            if not _draft_ready(prefix):
                st.warning("Выберите хотя бы одну точку или другой способ привязки в «Дополнительно».")
            else:
                st.session_state[index_key] = index + 1
                st.rerun()
    else:
        if action.button(
            f"Сохранить все изображения · {len(image_files)}",
            type="primary",
            width="stretch",
            key=f"univimg_save_{batch}",
        ):
            if errors:
                st.warning("Не закончена разметка: " + ", ".join(errors[:8]))
                return
            if not prepared:
                st.warning("Нет изображений для сохранения.")
                return
            created, save_errors = _save_prepared_batch(int(project_id), prepared)
            if save_errors:
                for message in save_errors:
                    st.error(message)
                return
            st.success(f"Сохранено изображений: {len(created)}. Привязки закреплены за analysis_id.")
            prefix_to_clear = f"univimg_{batch}_"
            for key in list(st.session_state):
                if str(key).startswith(prefix_to_clear) or key == index_key:
                    st.session_state.pop(key, None)
            st.rerun()
