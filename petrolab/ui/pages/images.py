from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import apply_quick_filter, dataset_label, row_identity
from petrolab.db import list_datasets, load_dataset_dataframe
from petrolab.services.image_service import (
    ImageAssignment,
    ImagePayload,
    ImageScope,
    SCOPE_ANALYSIS,
    SCOPE_DATASET,
    SCOPE_FIELD,
    create_assigned_image_batch,
    delete_image_asset,
    list_dataset_images,
)
from petrolab.ui.components import render_asset_gallery, render_project_selector

IMAGE_KINDS = [
    "BSE", "EDS", "Оптическая микрофотография", "Карта элементов",
    "Фото образца", "Другое",
]
SCOPE_LABELS = {
    "К нескольким точкам анализа": SCOPE_ANALYSIS,
    "К образцу / зерну / поколению": SCOPE_FIELD,
    "Ко всему набору": SCOPE_DATASET,
    "Не импортировать": "skip",
}


def render_images_page() -> None:
    st.title("Изображения и аналитические точки")
    st.caption(
        "Сначала импортируйте анализы, затем загрузите пачку фотографий. ПетроЛаб попросит "
        "отдельно указать связь для каждого изображения; одна BSE может быть связана сразу с несколькими точками."
    )
    project = render_project_selector("images_project")
    if project is None:
        return

    datasets = list_datasets(int(project["id"]))
    if not datasets:
        st.info("Сначала импортируйте хотя бы один набор анализов.")
        return

    dataset_map = {dataset_label(dataset): dataset for dataset in datasets}
    chosen = dataset_map[st.selectbox("Набор данных", list(dataset_map), key="img_dataset")]
    dataframe = load_dataset_dataframe(int(chosen["id"]), include_meta=True)

    wizard_tab, gallery_tab = st.tabs(["Новая пачка изображений", "Галерея набора"])
    with wizard_tab:
        _render_batch_wizard(int(project["id"]), chosen, dataframe)
    with gallery_tab:
        _render_dataset_gallery(int(chosen["id"]), dataframe)


def _render_batch_wizard(project_id: int, dataset: dict, dataframe: pd.DataFrame) -> None:
    files = st.file_uploader(
        "Загрузите фотографии",
        type=["png", "jpg", "jpeg", "webp", "tif", "tiff"],
        accept_multiple_files=True,
        key=f"image_batch_upload_{dataset['id']}",
    )
    if not files:
        st.info("Можно выбрать сразу 10, 20 или больше изображений. Они не сохранятся, пока не будет подтверждена вся пачка.")
        return

    entries = []
    for index, file in enumerate(files):
        data = file.getvalue()
        digest = hashlib.sha256(data).hexdigest()[:12]
        entries.append((index, file.name, data, f"{index}_{digest}"))

    index_key = f"image_wizard_index_{dataset['id']}"
    if index_key not in st.session_state:
        st.session_state[index_key] = 0
    st.session_state[index_key] = min(int(st.session_state[index_key]), len(entries) - 1)
    current_index = int(st.session_state[index_key])
    _, filename, data, token = entries[current_index]

    st.progress((current_index + 1) / len(entries), text=f"Изображение {current_index + 1} из {len(entries)}")
    st.subheader(filename)
    try:
        st.image(data, caption=filename, width=850)
    except Exception:
        st.warning("Streamlit не смог показать предпросмотр этого формата, но файл всё равно можно сохранить.")

    prefix = f"imgwiz_{dataset['id']}_{token}"
    c1, c2 = st.columns(2)
    c1.selectbox("Тип изображения", IMAGE_KINDS, key=f"{prefix}_kind")
    c2.text_input("Подпись", value=Path(filename).stem, key=f"{prefix}_title")
    scope_label = st.radio(
        "К чему относится эта фотография?",
        list(SCOPE_LABELS),
        horizontal=True,
        key=f"{prefix}_scope",
    )
    scope_type = SCOPE_LABELS[scope_label]

    if scope_type == SCOPE_ANALYSIS:
        _render_multi_point_controls(prefix, dataframe)
    elif scope_type == SCOPE_FIELD:
        _render_field_controls(prefix, dataframe)
    elif scope_type == SCOPE_DATASET:
        st.caption("Фотография будет видна для всего выбранного набора данных.")
    else:
        st.caption("Эта фотография останется в выбранной пачке, но при сохранении будет пропущена.")

    nav1, nav2, nav3 = st.columns([1, 1, 2])
    if nav1.button("← Предыдущее", disabled=current_index == 0, key=f"{prefix}_prev"):
        st.session_state[index_key] = current_index - 1
        st.rerun()
    if nav2.button("Следующее →", disabled=current_index >= len(entries) - 1, key=f"{prefix}_next"):
        error = _assignment_error(prefix, scope_type)
        if error:
            st.error(error)
        else:
            st.session_state[index_key] = current_index + 1
            st.rerun()
    if nav3.button("Перейти к проверке всей пачки", key=f"{prefix}_review"):
        st.session_state[index_key] = len(entries) - 1

    st.divider()
    _render_batch_summary(project_id, dataset, dataframe, entries)


def _render_multi_point_controls(prefix: str, dataframe: pd.DataFrame) -> None:
    query = st.text_input(
        "Поиск по образцу / зерну / точке",
        key=f"{prefix}_point_query",
        placeholder="Например: N-7, зерно 14 или N-X1",
    )
    filtered = apply_quick_filter(dataframe, query)
    option_map = _analysis_option_map(filtered.head(5000))
    previously = st.session_state.get(f"{prefix}_analysis_ids", [])
    available_ids = set(option_map.values())
    retained = [value for value in previously if value in available_ids]
    selected_labels = st.multiselect(
        "Точки, видимые на этой фотографии",
        list(option_map),
        default=[label for label, value in option_map.items() if value in retained],
        key=f"{prefix}_analysis_labels",
    )
    st.session_state[f"{prefix}_analysis_ids"] = [option_map[label] for label in selected_labels]
    st.caption(f"Выбрано точек: {len(st.session_state[f'{prefix}_analysis_ids'])}.")


def _render_field_controls(prefix: str, dataframe: pd.DataFrame) -> None:
    candidates = [
        column for column in dataframe.columns
        if not str(column).startswith("_") and dataframe[column].nunique(dropna=True) <= 500
    ]
    preferred = [column for column in ["Sample", "Grain", "Generation"] if column in candidates]
    candidates = preferred + [column for column in candidates if column not in preferred]
    if not candidates:
        st.warning("В наборе нет подходящего поля для такой привязки.")
        return
    column = st.selectbox("Поле", candidates, key=f"{prefix}_field_column")
    values = sorted(dataframe[column].dropna().astype(str).unique().tolist())
    st.selectbox("Значение", values, key=f"{prefix}_field_value") if values else None


def _analysis_option_map(dataframe: pd.DataFrame) -> dict[str, str]:
    result: dict[str, str] = {}
    for _, row in dataframe.iterrows():
        analysis_id = str(row["_analysis_id"])
        label = f"{row_identity(row)} · Excel {row.get('_source_row', '—')} · {analysis_id[:8]}"
        if label in result:
            label = f"{label} · {analysis_id[8:12]}"
        result[label] = analysis_id
    return result


def _assignment_error(prefix: str, scope_type: str) -> str | None:
    if scope_type == SCOPE_ANALYSIS and not st.session_state.get(f"{prefix}_analysis_ids"):
        return "Выберите хотя бы одну аналитическую точку или другой тип привязки."
    if scope_type == SCOPE_FIELD:
        if not st.session_state.get(f"{prefix}_field_column") or not st.session_state.get(f"{prefix}_field_value"):
            return "Выберите поле и значение."
    return None


def _render_batch_summary(
    project_id: int,
    dataset: dict,
    dataframe: pd.DataFrame,
    entries: list[tuple[int, str, bytes, str]],
) -> None:
    rows = []
    assignments: list[ImageAssignment] = []
    errors: list[str] = []

    for _, filename, data, token in entries:
        prefix = f"imgwiz_{dataset['id']}_{token}"
        scope_label = st.session_state.get(f"{prefix}_scope", "К нескольким точкам анализа")
        scope_type = SCOPE_LABELS[scope_label]
        kind = st.session_state.get(f"{prefix}_kind", IMAGE_KINDS[0])
        title = st.session_state.get(f"{prefix}_title", Path(filename).stem)
        if scope_type == "skip":
            rows.append({"Файл": filename, "Тип": kind, "Связь": "Пропустить", "Готово": "да"})
            continue

        error = _assignment_error(prefix, scope_type)
        if error:
            errors.append(f"{filename}: {error}")
            rows.append({"Файл": filename, "Тип": kind, "Связь": error, "Готово": "нет"})
            continue

        if scope_type == SCOPE_ANALYSIS:
            ids = tuple(st.session_state.get(f"{prefix}_analysis_ids", []))
            scope = ImageScope(SCOPE_ANALYSIS, analysis_ids=ids)
            link_text = f"точек: {len(ids)}"
        elif scope_type == SCOPE_FIELD:
            column = st.session_state.get(f"{prefix}_field_column", "")
            value = st.session_state.get(f"{prefix}_field_value", "")
            scope = ImageScope(SCOPE_FIELD, scope_column=column, scope_value=value)
            link_text = f"{column} = {value}"
        else:
            scope = ImageScope(SCOPE_DATASET)
            link_text = "весь набор"

        assignments.append(ImageAssignment(ImagePayload(filename, data), scope, kind, title))
        rows.append({"Файл": filename, "Тип": kind, "Связь": link_text, "Готово": "да"})

    with st.expander("Проверка всей пачки", expanded=False):
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        if errors:
            st.warning("Нужно закончить настройку: " + " | ".join(errors))
        if st.button(
            "Сохранить всю настроенную пачку",
            type="primary",
            disabled=bool(errors) or not assignments,
            key=f"save_image_batch_{dataset['id']}",
        ):
            try:
                result = create_assigned_image_batch(
                    project_id=project_id,
                    dataset_id=int(dataset["id"]),
                    assignments=assignments,
                )
                st.success(f"Сохранено изображений: {result.count}.")
                _clear_wizard_state(int(dataset["id"]))
                st.rerun()
            except Exception as exc:
                st.error(f"Пачка не сохранена: {exc}")


def _clear_wizard_state(dataset_id: int) -> None:
    prefixes = (f"imgwiz_{dataset_id}_", f"image_wizard_index_{dataset_id}")
    for key in list(st.session_state):
        if any(str(key).startswith(prefix) for prefix in prefixes):
            del st.session_state[key]


def _render_dataset_gallery(dataset_id: int, dataframe: pd.DataFrame) -> None:
    st.subheader("Галерея набора")
    assets = list_dataset_images(dataset_id)
    if not assets:
        st.caption("Изображений пока нет.")
        return

    id_to_label = {
        str(row["_analysis_id"]): row_identity(row)
        for _, row in dataframe.iterrows()
    }
    for asset in assets[:200]:
        title = asset["title"] or asset["original_filename"]
        with st.expander(f"{asset['kind']} · {title} · {asset['scope_type']}"):
            render_asset_gallery([asset], max_items=1, width=850)
            st.write(f"**Исходное имя:** {asset['original_filename']}")
            analysis_ids = asset.get("analysis_ids") or []
            if analysis_ids:
                labels = [id_to_label.get(value, value[:8]) for value in analysis_ids]
                st.write("**Точки:** " + "; ".join(labels))
            if asset.get("scope_column"):
                st.write(f"**Связь:** {asset['scope_column']} = {asset['scope_value']}")
            path = Path(asset["stored_path"])
            st.caption(f"Локальное хранилище: {path.name}")
            if st.button("Удалить изображение", key=f"delete_asset_{asset['id']}"):
                try:
                    delete_image_asset(int(asset["id"]))
                    st.success("Изображение удалено.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Не удалось удалить изображение: {exc}")
