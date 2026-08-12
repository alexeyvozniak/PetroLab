from __future__ import annotations

from pathlib import Path

import streamlit as st

from petrolab.dataframe_utils import apply_quick_filter, dataset_label, row_identity
from petrolab.db import list_datasets, load_dataset_dataframe
from petrolab.services.image_service import (
    ImagePayload,
    ImageScope,
    SCOPE_ANALYSIS,
    SCOPE_DATASET,
    SCOPE_FIELD,
    create_image_assets,
    delete_image_asset,
    list_dataset_images,
)
from petrolab.ui.components import render_asset_gallery, render_project_selector

IMAGE_KINDS = [
    "BSE",
    "EDS",
    "Оптическая микрофотография",
    "Карта элементов",
    "Фото образца",
    "Другое",
]


def render_images_page() -> None:
    """Render image linking and gallery management without direct filesystem writes."""
    st.title("Изображения и аналитические точки")
    st.caption(
        "Изображение можно связать со всем набором, с образцом/зерном через значение поля "
        "или с одной конкретной аналитической точкой. Файловые операции выполняет image_service."
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
    _render_image_link_form(int(project["id"]), chosen, dataframe)
    _render_dataset_gallery(int(chosen["id"]))


def _render_image_link_form(project_id: int, dataset: dict, dataframe) -> None:
    query = st.text_input("Найти точку/образец/зерно", key="img_search")
    filtered = apply_quick_filter(dataframe, query)

    scope_type = st.radio(
        "Привязать изображение к",
        [SCOPE_DATASET, SCOPE_FIELD, SCOPE_ANALYSIS],
        horizontal=True,
    )
    scope = _render_scope_controls(scope_type, filtered)
    kind = st.selectbox("Тип изображения", IMAGE_KINDS)
    title = st.text_input("Подпись/название изображения")
    files = st.file_uploader(
        "Изображения",
        type=["png", "jpg", "jpeg", "webp", "tif", "tiff"],
        accept_multiple_files=True,
        key="image_upload",
    )

    if st.button("Привязать изображения", type="primary", disabled=not files):
        try:
            payloads = [ImagePayload(file.name, file.getvalue()) for file in files or []]
            result = create_image_assets(
                project_id=project_id,
                dataset_id=int(dataset["id"]),
                images=payloads,
                scope=scope,
                kind=kind,
                title=title,
            )
            st.success(f"Привязано изображений: {result.count}.")
            st.rerun()
        except Exception as exc:
            st.error(f"Не удалось сохранить изображения: {exc}")


def _render_scope_controls(scope_type: str, dataframe) -> ImageScope:
    if scope_type == SCOPE_DATASET:
        return ImageScope(SCOPE_DATASET)

    if scope_type == SCOPE_FIELD:
        candidates = [
            column
            for column in dataframe.columns
            if not str(column).startswith("_") and dataframe[column].nunique(dropna=True) <= 300
        ]
        if not candidates:
            st.warning("В наборе нет подходящего поля для такой привязки.")
            return ImageScope(SCOPE_FIELD)
        column = st.selectbox("Поле", candidates, key="img_scope_column")
        values = dataframe[column].dropna().astype(str).unique().tolist()
        value = st.selectbox("Значение", values, key="img_scope_value") if values else ""
        return ImageScope(SCOPE_FIELD, scope_column=column, scope_value=value)

    if dataframe.empty:
        st.warning("По текущему фильтру нет аналитических точек.")
        return ImageScope(SCOPE_ANALYSIS)

    option_map: dict[str, str] = {}
    for _, row in dataframe.head(3000).iterrows():
        label = (
            f"{row_identity(row)} · строка {row.get('_source_row', '—')} · "
            f"{str(row['_analysis_id'])[:8]}"
        )
        option_map[label] = str(row["_analysis_id"])
    selected = st.selectbox("Аналитическая точка", list(option_map), key="img_analysis_id")
    return ImageScope(SCOPE_ANALYSIS, analysis_id=option_map[selected])


def _render_dataset_gallery(dataset_id: int) -> None:
    st.subheader("Галерея набора")
    assets = list_dataset_images(dataset_id)
    if not assets:
        st.caption("Изображений пока нет.")
        return

    for asset in assets[:100]:
        title = asset["title"] or asset["original_filename"]
        with st.expander(f"{asset['kind']} · {title} · {asset['scope_type']}"):
            render_asset_gallery([asset], max_items=1, width=700)
            st.write(f"**Исходное имя:** {asset['original_filename']}")
            if asset.get("analysis_id"):
                st.code(asset["analysis_id"])
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
