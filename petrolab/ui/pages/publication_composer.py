from __future__ import annotations

import hashlib

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab.publication_composer import (
    LABEL_MODE_TITLES,
    build_publication_figure,
    default_panel_label,
    figure_bytes,
    panel_label_sequence,
    publication_recipe,
    recipe_json_bytes,
)
from petrolab.publication_sources import project_publication_sources, source_bytes
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.project_context import active_project
from petrolab.visualization_presets import FIGURE_PRESETS


_ALLOWED_TYPES = ["png", "jpg", "jpeg", "tif", "tiff", "webp"]


def _upload_sources(uploads) -> list[dict]:
    sources: list[dict] = []
    for index, upload in enumerate(uploads or []):
        content = upload.getvalue()
        digest = hashlib.sha256(content).hexdigest()[:20]
        sources.append({
            "source_id": f"upload:{digest}:{index}",
            "source_name": str(upload.name),
            "group": "Загружено сейчас",
            "note": "",
            "image_bytes": content,
        })
    return sources


def _source_fingerprint(sources: list[dict]) -> str:
    digest = hashlib.sha256()
    for index, source in enumerate(sources):
        digest.update(str(index).encode("ascii"))
        digest.update(str(source.get("source_id", "")).encode("utf-8", errors="replace"))
        content = source.get("image_bytes")
        if isinstance(content, (bytes, bytearray)):
            digest.update(hashlib.sha256(bytes(content)).digest())
        else:
            digest.update(str(source.get("path", "")).encode("utf-8", errors="replace"))
    return digest.hexdigest()


def _default_editor(sources: list[dict], mode: str, font_size: float) -> pd.DataFrame:
    labels = panel_label_sequence(len(sources), mode)
    rows: list[dict] = []
    for index, source in enumerate(sources):
        rows.append({
            "Порядок": index + 1,
            "Источник": f"{source.get('group', '')} · {source.get('source_name', '')}".strip(" ·"),
            "Заголовок": "",
            "Метка": labels[index],
            "Показывать метку": bool(labels[index]),
            "X метки": 0.025,
            "Y метки": 0.975,
            "Размер метки": float(font_size),
            "Жирная": True,
            "Заполнение": "Вместить",
            "_source_id": str(source.get("source_id", "")),
        })
    return pd.DataFrame(rows)


def _reset_auto_labels(dataframe: pd.DataFrame, mode: str, show_all: bool) -> pd.DataFrame:
    updated = dataframe.copy()
    labels = panel_label_sequence(len(updated), mode)
    for row_index, label in enumerate(labels):
        updated.at[row_index, "Метка"] = label
        updated.at[row_index, "Показывать метку"] = bool(label) and bool(show_all)
    return updated


def _read_source(source: dict) -> bytes:
    content = source.get("image_bytes")
    if isinstance(content, (bytes, bytearray)):
        return bytes(content)
    return source_bytes(source)


def _panels_from_editor(sources: list[dict], editor: pd.DataFrame, show_all: bool) -> list[dict]:
    source_map = {str(source.get("source_id")): source for source in sources}
    rows = editor.copy()
    rows["Порядок"] = pd.to_numeric(rows["Порядок"], errors="coerce")
    rows["_stable"] = range(len(rows))
    rows = rows.sort_values(["Порядок", "_stable"], kind="mergesort", na_position="last")
    panels: list[dict] = []
    for _, row in rows.iterrows():
        source_id = str(row.get("_source_id", ""))
        source = source_map.get(source_id)
        if source is None:
            continue
        crop_mode = "cover" if str(row.get("Заполнение", "Вместить")) == "Заполнить" else "contain"
        label = default_panel_label(
            str(row.get("Метка", "")),
            enabled=bool(show_all) and bool(row.get("Показывать метку", True)),
            x=float(row.get("X метки", 0.025)),
            y=float(row.get("Y метки", 0.975)),
            font_size=float(row.get("Размер метки", 11.0)),
            font_weight="bold" if bool(row.get("Жирная", True)) else "normal",
        )
        try:
            image_bytes = _read_source(source)
        except Exception:
            # Keep the panel cell in place. The composer engine will draw an
            # explicit broken-source message instead of shifting later panels.
            image_bytes = b""
        panels.append({
            "source_id": source_id,
            "source_name": str(source.get("source_name") or source_id),
            "image_bytes": image_bytes,
            "title": str(row.get("Заголовок", "") or ""),
            "crop_mode": crop_mode,
            "label": label,
        })
    return panels


def _project_source_selector(project: dict | None) -> list[dict]:
    if project is None:
        return []
    try:
        available = project_publication_sources(int(project["id"]))
    except Exception as exc:
        st.warning(f"Не удалось прочитать изображения проекта: {exc}")
        return []
    if not available:
        st.caption("В проекте пока нет сохранённых изображений, пригодных для панели.")
        return []
    by_id = {str(source["source_id"]): source for source in available}
    selected_ids = st.multiselect(
        "Взять из текущего проекта",
        list(by_id),
        format_func=lambda value: f"{by_id[str(value)]['group']} · {by_id[str(value)]['source_name']}",
        key="publication_composer_project_sources",
        placeholder="Фото пород, изображения анализов, шлифы…",
    )
    selected = [by_id[str(value)] for value in selected_ids if str(value) in by_id]
    fallback_notes = [str(item.get("note")) for item in selected if str(item.get("note", "")).strip()]
    if fallback_notes:
        st.warning("\n".join(dict.fromkeys(fallback_notes)))
    return selected


def render_publication_composer_page() -> None:
    project = active_project()
    render_page_header(
        "Редактор мультипанельных рисунков",
        "Соберите один журнальный рисунок из выбранных изображений. PetroLab автоматически расставит A/B/C или А/Б/В, но каждую метку можно переименовать, выключить и передвинуть.",
        eyebrow="Публикация",
        context=str(project["name"]) if project else "Без проекта",
    )

    render_section_header("Источники панелей", "Можно смешивать изображения из проекта и новые файлы")
    project_sources = _project_source_selector(project)
    uploads = st.file_uploader(
        "Или добавить файлы с компьютера",
        type=_ALLOWED_TYPES,
        accept_multiple_files=True,
        key="publication_composer_uploads",
        help="PNG, JPEG, TIFF и WEBP. Можно добавить уже экспортированные графики PetroLab.",
    )
    sources = [*project_sources, *_upload_sources(uploads)]
    if not sources:
        st.info("Выберите изображения из проекта или добавьте файлы с компьютера.")
        return
    if len(sources) > 12:
        st.warning("В одной фигуре сейчас поддерживается до 12 панелей. Используются первые 12 выбранных источников.")
        sources = sources[:12]

    preset_names = list(FIGURE_PRESETS)
    p1, p2, p3 = st.columns(3)
    preset_name = p1.selectbox(
        "Журнальный preset",
        preset_names,
        index=preset_names.index("Lithos") if "Lithos" in preset_names else 0,
        key="publication_composer_preset",
    )
    preset = FIGURE_PRESETS[preset_name]
    mode_by_title = {title: key for key, title in LABEL_MODE_TITLES.items()}
    selected_mode_title = p2.selectbox(
        "Автоматические метки",
        list(mode_by_title),
        index=list(mode_by_title).index("A, B, C…") if "A, B, C…" in mode_by_title else 0,
        key="publication_composer_label_mode",
    )
    label_mode = mode_by_title[selected_mode_title]
    show_all = p3.checkbox("Показывать метки", value=True, key="publication_composer_show_labels")

    default_label_size = max(float(preset.font_size) + 2.0, 10.0)
    fingerprint = _source_fingerprint(sources)
    previous_fingerprint = str(st.session_state.get("_publication_composer_fingerprint", ""))
    if fingerprint != previous_fingerprint:
        st.session_state["_publication_composer_config"] = _default_editor(
            sources,
            label_mode,
            default_label_size,
        )
        st.session_state["_publication_composer_fingerprint"] = fingerprint
        st.session_state["_publication_composer_editor_revision"] = int(
            st.session_state.get("_publication_composer_editor_revision", 0)
        ) + 1

    controls = st.columns([1, 1, 2])
    if controls[0].button("Сбросить метки по схеме", key="publication_reset_labels"):
        current = st.session_state.get("_publication_composer_config")
        if isinstance(current, pd.DataFrame):
            st.session_state["_publication_composer_config"] = _reset_auto_labels(
                current,
                label_mode,
                show_all,
            )
            st.session_state["_publication_composer_editor_revision"] = int(
                st.session_state.get("_publication_composer_editor_revision", 0)
            ) + 1
            st.rerun()
    controls[1].caption("Смена схемы сама по себе не перезаписывает ручные метки.")

    render_section_header("Панели", "Порядок, подписи и положение меток")
    config = st.session_state.get("_publication_composer_config")
    if not isinstance(config, pd.DataFrame) or len(config) != len(sources):
        config = _default_editor(sources, label_mode, default_label_size)
        st.session_state["_publication_composer_config"] = config
    revision = int(st.session_state.get("_publication_composer_editor_revision", 0))
    edited = st.data_editor(
        config,
        width="stretch",
        hide_index=True,
        disabled=["Источник", "_source_id"],
        column_config={
            "Порядок": st.column_config.NumberColumn("Порядок", min_value=1, max_value=12, step=1),
            "Источник": st.column_config.TextColumn("Источник"),
            "Заголовок": st.column_config.TextColumn("Заголовок панели"),
            "Метка": st.column_config.TextColumn("Метка"),
            "Показывать метку": st.column_config.CheckboxColumn("Метка включена"),
            "X метки": st.column_config.NumberColumn("X", min_value=-0.25, max_value=1.25, step=0.01, format="%.3f"),
            "Y метки": st.column_config.NumberColumn("Y", min_value=-0.25, max_value=1.25, step=0.01, format="%.3f"),
            "Размер метки": st.column_config.NumberColumn("Размер", min_value=4.0, max_value=40.0, step=0.5),
            "Жирная": st.column_config.CheckboxColumn("Жирная"),
            "Заполнение": st.column_config.SelectboxColumn("Вписать", options=["Вместить", "Заполнить"]),
            "_source_id": None,
        },
        key=f"publication_composer_editor_{revision}",
    )
    st.session_state["_publication_composer_config"] = edited.copy()
    st.caption("X/Y — положение метки внутри панели: (0, 0) слева снизу, (1, 1) справа сверху. Значения немного за пределами 0–1 позволяют вынести букву наружу.")

    render_section_header("Макет", "Размер фигуры и сетка")
    l1, l2, l3, l4 = st.columns(4)
    auto_columns = 2 if len(sources) <= 6 else 3
    columns = l1.selectbox(
        "Колонок",
        [1, 2, 3, 4],
        index=[1, 2, 3, 4].index(auto_columns),
        key="publication_composer_columns",
    )
    width_in = l2.number_input(
        "Ширина, inch",
        min_value=2.0,
        max_value=20.0,
        value=float(max(preset.width_in, 7.2)),
        step=0.1,
        key="publication_composer_width",
    )
    panel_height = l3.number_input(
        "Высота панели, inch",
        min_value=1.0,
        max_value=10.0,
        value=3.2,
        step=0.1,
        key="publication_composer_panel_height",
    )
    dpi = l4.selectbox("DPI", [300, 600], index=1, key="publication_composer_dpi")

    panels = _panels_from_editor(sources, edited, show_all)
    if not panels:
        st.error("Не удалось сформировать список панелей.")
        return
    try:
        figure = build_publication_figure(
            panels,
            columns=int(columns),
            width_in=float(width_in),
            panel_height_in=float(panel_height),
            font_family=str(preset.font_family),
        )
    except Exception as exc:
        st.error(f"Не удалось собрать рисунок: {exc}")
        return

    render_badges([
        (f"панелей · {len(panels)}", "accent"),
        (f"сетка · {columns} кол.", "neutral"),
        (f"{preset.title}", "success"),
    ])
    st.pyplot(figure, width="stretch")

    recipe = publication_recipe(
        panels,
        columns=int(columns),
        width_in=float(width_in),
        panel_height_in=float(panel_height),
        font_family=str(preset.font_family),
        journal_preset=str(preset_name),
    )
    render_section_header("Экспорт", "Метки входят в сам файл рисунка")
    e1, e2, e3, e4 = st.columns(4)
    e1.download_button(
        "PNG",
        figure_bytes(figure, "png", int(dpi)),
        file_name="petrolab_publication_figure.png",
        mime="image/png",
        width="stretch",
    )
    e2.download_button(
        "SVG",
        figure_bytes(figure, "svg", int(dpi)),
        file_name="petrolab_publication_figure.svg",
        mime="image/svg+xml",
        width="stretch",
    )
    e3.download_button(
        "TIFF",
        figure_bytes(figure, "tiff", int(dpi)),
        file_name="petrolab_publication_figure.tiff",
        mime="image/tiff",
        width="stretch",
    )
    e4.download_button(
        "Recipe JSON",
        recipe_json_bytes(recipe),
        file_name="petrolab_publication_figure.recipe.json",
        mime="application/json",
        width="stretch",
    )
    plt.close(figure)
