from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import apply_quick_filter, dataset_label
from petrolab.db import list_datasets, load_dataset_dataframe
from petrolab.services.image_service import (
    ImageAssignment, ImagePayload, ImageScope,
    SCOPE_ANALYSIS, SCOPE_DATASET, SCOPE_FIELD,
    create_assigned_image_batch, delete_image_asset, list_dataset_images,
    relink_image_asset,
)
from petrolab.ui.components import render_asset_gallery, render_project_selector
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.pages import images as legacy


def _entry_state(dataset_id: int, token: str) -> tuple[str, bool]:
    prefix = f"imgwiz_{dataset_id}_{token}"
    scope_label = st.session_state.get(f"{prefix}_scope", "К нескольким точкам анализа")
    scope_type = legacy.SCOPE_LABELS.get(scope_label, SCOPE_ANALYSIS)
    return prefix, legacy._assignment_error(prefix, scope_type) is None


def _assignment(prefix: str, filename: str, data: bytes) -> ImageAssignment | None:
    scope_label = st.session_state.get(f"{prefix}_scope", "К нескольким точкам анализа")
    scope_type = legacy.SCOPE_LABELS[scope_label]
    if scope_type == "skip":
        return None
    if legacy._assignment_error(prefix, scope_type):
        raise ValueError("Настройка изображения не завершена")
    if scope_type == SCOPE_ANALYSIS:
        scope = ImageScope(SCOPE_ANALYSIS, analysis_ids=tuple(st.session_state.get(f"{prefix}_analysis_ids", [])))
    elif scope_type == SCOPE_FIELD:
        scope = ImageScope(SCOPE_FIELD, scope_column=st.session_state.get(f"{prefix}_field_column", ""), scope_value=st.session_state.get(f"{prefix}_field_value", ""))
    else:
        scope = ImageScope(SCOPE_DATASET)
    return ImageAssignment(
        ImagePayload(filename, data), scope,
        st.session_state.get(f"{prefix}_kind", legacy.IMAGE_KINDS[0]),
        st.session_state.get(f"{prefix}_title", Path(filename).stem),
    )


def _wizard(project_id: int, dataset: dict, dataframe: pd.DataFrame) -> None:
    dataset_id = int(dataset["id"])
    epoch = int(st.session_state.get(f"image_upload_epoch_{dataset_id}", 0))
    files = st.file_uploader(
        "Фотографии", type=["png", "jpg", "jpeg", "webp", "tif", "tiff"],
        accept_multiple_files=True, key=f"image_batch_upload_{dataset_id}_{epoch}",
    )
    if not files:
        st.caption("Можно выбрать сразу всю пачку. Файлы сохранятся только после общей проверки.")
        return
    entries = [(file.name, file.getvalue(), f"{i}_{hashlib.sha256(file.getvalue()).hexdigest()[:10]}") for i, file in enumerate(files)]
    index_key = f"image_wizard_index_{dataset_id}"
    st.session_state[index_key] = min(int(st.session_state.get(index_key, 0)), len(entries) - 1)
    index = int(st.session_state[index_key])
    filename, data, token = entries[index]
    prefix, _ = _entry_state(dataset_id, token)

    status_items = []
    for i, (name, _, item_token) in enumerate(entries):
        _, ready = _entry_state(dataset_id, item_token)
        marker = "→" if i == index else ("✓" if ready and i < index else "○")
        status_items.append((f"{marker} {name}", "success" if marker == "✓" else "accent" if marker == "→" else "neutral"))
    render_badges(status_items[:12])
    if len(status_items) > 12:
        st.caption(f"Ещё файлов: {len(status_items) - 12}")
    st.progress((index + 1) / len(entries), text=f"{index + 1} из {len(entries)} · {filename}")

    left, right = st.columns([1.35, 1])
    with left:
        try:
            st.image(data, caption=filename, width="stretch")
        except Exception:
            st.info("Предпросмотр этого формата недоступен, но файл можно сохранить.")
    with right:
        st.selectbox("Тип", legacy.IMAGE_KINDS, key=f"{prefix}_kind")
        st.text_input("Подпись", value=Path(filename).stem, key=f"{prefix}_title")
        scope_label = st.radio("Связать с", list(legacy.SCOPE_LABELS), key=f"{prefix}_scope")
        scope_type = legacy.SCOPE_LABELS[scope_label]
        if scope_type == SCOPE_ANALYSIS:
            legacy._render_multi_point_controls(prefix, dataframe)
        elif scope_type == SCOPE_FIELD:
            legacy._render_field_controls(prefix, dataframe)
        elif scope_type == SCOPE_DATASET:
            st.caption("Изображение относится ко всему набору.")
        else:
            st.caption("Файл будет пропущен при сохранении.")

    p, n, review = st.columns([1, 1, 2])
    if p.button("← Назад", disabled=index == 0, width="stretch"):
        st.session_state[index_key] = index - 1; st.rerun()
    if n.button("Далее →", disabled=index == len(entries) - 1, type="primary", width="stretch"):
        error = legacy._assignment_error(prefix, scope_type)
        if error: st.error(error)
        else: st.session_state[index_key] = index + 1; st.rerun()

    assignments, errors = [], []
    for name, raw, item_token in entries:
        item_prefix, _ = _entry_state(dataset_id, item_token)
        try:
            item = _assignment(item_prefix, name, raw)
            if item is not None: assignments.append(item)
        except ValueError:
            errors.append(name)
    if review.button("Проверить и сохранить пачку", width="stretch"):
        if errors:
            st.warning("Не закончена настройка: " + ", ".join(errors[:8]))
        elif assignments:
            result = create_assigned_image_batch(project_id=project_id, dataset_id=dataset_id, assignments=assignments)
            st.success(f"Сохранено изображений: {result.count}.")
            legacy._clear_wizard_state(dataset_id); st.rerun()


def _repair_detached(asset: dict, dataframe: pd.DataFrame) -> None:
    asset_id = int(asset["id"])
    with st.expander("Восстановить привязку", expanded=False):
        query = st.text_input(
            "Поиск точки", placeholder="Sample, Grain, Point, Generation…",
            key=f"repair_image_query_{asset_id}",
        )
        candidates = apply_quick_filter(dataframe, query) if query else dataframe
        limit = 5000
        if len(candidates) > limit:
            st.caption(f"Найдено {len(candidates)} точек; показаны первые {limit}. Уточните поиск.")
        labels = legacy._analysis_id_labels(candidates.head(limit))
        selected = st.multiselect(
            "Новые точки для изображения",
            list(labels),
            format_func=lambda analysis_id: labels.get(analysis_id, analysis_id[:8]),
            key=f"repair_image_points_{asset_id}",
        )
        if st.button(
            "Восстановить привязку", type="primary", disabled=not selected,
            key=f"repair_image_save_{asset_id}", width="stretch",
        ):
            try:
                relink_image_asset(asset_id, selected)
                st.success("Привязка восстановлена.")
                st.rerun()
            except Exception as exc:
                st.error(f"Не удалось восстановить привязку: {exc}")


def _gallery(dataset_id: int, dataframe: pd.DataFrame) -> None:
    assets = list_dataset_images(dataset_id)
    render_section_header("Галерея", f"{len(assets)} изображений")
    if not assets:
        st.caption("Изображений пока нет."); return
    shown = assets[:120]
    if len(assets) > len(shown):
        st.caption(f"Показано {len(shown)} из {len(assets)}. Для больших архивов используйте фильтрацию по набору.")
    columns = st.columns(3)
    for i, asset in enumerate(shown):
        with columns[i % 3]:
            render_asset_gallery([asset], max_items=1)
            if str(asset.get("link_status") or "") == "detached":
                _repair_detached(asset, dataframe)
            confirm_key = f"confirm_delete_image_{asset['id']}"
            if not st.session_state.get(confirm_key):
                if st.button("Удалить…", key=f"ask_delete_image_{asset['id']}"):
                    st.session_state[confirm_key] = True; st.rerun()
            else:
                st.caption("Удаление нельзя отменить.")
                yes, no = st.columns(2)
                if yes.button("Да, удалить", key=f"yes_delete_image_{asset['id']}"):
                    delete_image_asset(int(asset["id"])); st.session_state.pop(confirm_key, None); st.rerun()
                if no.button("Отмена", key=f"no_delete_image_{asset['id']}"):
                    st.session_state.pop(confirm_key, None); st.rerun()


def render_images_dashboard_page() -> None:
    render_page_header("Изображения", "Связывайте BSE, EDS, карты и фотографии с аналитическими точками без потери контекста.", eyebrow="Материалы")
    project = render_project_selector("images_project")
    if project is None: return
    datasets = list_datasets(int(project["id"]))
    if not datasets:
        st.info("Сначала импортируйте хотя бы один набор анализов."); return
    mapping = {dataset_label(item): item for item in datasets}
    dataset = mapping[st.selectbox("Набор данных", list(mapping), key="img_dataset")]
    dataframe = load_dataset_dataframe(int(dataset["id"]), include_meta=True)
    wizard_tab, gallery_tab = st.tabs(["Добавить изображения", "Галерея"])
    with wizard_tab: _wizard(int(project["id"]), dataset, dataframe)
    with gallery_tab: _gallery(int(dataset["id"]), dataframe)
