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
    parse_publication_recipe_bytes,
    publication_recipe,
    recipe_json_bytes,
)
from petrolab.publication_sources import project_publication_sources, source_bytes
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.project_context import active_project
from petrolab.visualization_presets import FIGURE_PRESETS


_ALLOWED_TYPES = ["png", "jpg", "jpeg", "tif", "tiff", "webp"]
_EDITOR_COLUMNS = [
    "Порядок", "Источник", "Заголовок", "Метка", "Показывать метку",
    "X метки", "Y метки", "Размер метки", "Жирная", "Заполнение", "_source_id",
]


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


def _inbox_sources() -> list[dict]:
    raw = st.session_state.get("publication_composer_inbox", [])
    sources: list[dict] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or not item.get("source_id"):
            continue
        source_id = str(item["source_id"])
        if source_id in seen:
            continue
        seen.add(source_id)
        sources.append(dict(item))
    if not sources:
        return []
    c1, c2 = st.columns([3, 1])
    c1.success(f"Из PetroLab передано готовых графиков: {len(sources)}")
    if c2.button("Очистить переданные", key="publication_composer_clear_inbox", width="stretch"):
        st.session_state["publication_composer_inbox"] = []
        st.session_state.pop("_publication_composer_fingerprint", None)
        st.rerun()
    return sources


def _unique_sources(sources: list[dict]) -> tuple[list[dict], int]:
    unique: list[dict] = []
    seen: set[str] = set()
    duplicates = 0
    for source in sources:
        source_id = str(source.get("source_id") or "").strip()
        if not source_id:
            continue
        if source_id in seen:
            duplicates += 1
            continue
        seen.add(source_id)
        unique.append(source)
    return unique, duplicates


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


def _source_title(source: dict) -> str:
    return f"{source.get('group', '')} · {source.get('source_name', '')}".strip(" ·")


def _default_row(source: dict, order: int, label: str, font_size: float) -> dict:
    return {
        "Порядок": int(order),
        "Источник": _source_title(source),
        "Заголовок": "",
        "Метка": str(label),
        "Показывать метку": bool(label),
        "X метки": 0.025,
        "Y метки": 0.975,
        "Размер метки": float(font_size),
        "Жирная": True,
        "Заполнение": "Вместить",
        "_source_id": str(source.get("source_id", "")),
    }


def _default_editor(sources: list[dict], mode: str, font_size: float) -> pd.DataFrame:
    labels = panel_label_sequence(len(sources), mode)
    return pd.DataFrame([
        _default_row(source, index + 1, labels[index], font_size)
        for index, source in enumerate(sources)
    ], columns=_EDITOR_COLUMNS)


def _recipe_rows(recipe: dict) -> dict[str, dict]:
    result: dict[str, dict] = {}
    for index, panel in enumerate(recipe.get("panels", [])):
        source_id = str(panel.get("source_id") or "")
        label = dict(panel.get("label") or {})
        result[source_id] = {
            "Порядок": index + 1,
            "Заголовок": str(panel.get("title") or ""),
            "Метка": str(label.get("text") or ""),
            "Показывать метку": bool(label.get("enabled", bool(label.get("text")))),
            "X метки": float(label.get("x", 0.025)),
            "Y метки": float(label.get("y", 0.975)),
            "Размер метки": float(label.get("font_size", 11.0)),
            "Жирная": str(label.get("font_weight", "bold")) == "bold",
            "Заполнение": "Заполнить" if str(panel.get("crop_mode")) == "cover" else "Вместить",
        }
    return result


def _editor_from_recipe(
    sources: list[dict],
    recipe: dict,
    mode: str,
    font_size: float,
) -> tuple[pd.DataFrame, list[str]]:
    source_map = {str(source.get("source_id")): source for source in sources}
    recipe_map = _recipe_rows(recipe)
    rows: list[dict] = []
    missing: list[str] = []
    for source_id, settings in recipe_map.items():
        source = source_map.get(source_id)
        if source is None:
            missing.append(source_id)
            continue
        row = _default_row(source, int(settings["Порядок"]), str(settings["Метка"]), font_size)
        row.update(settings)
        rows.append(row)

    used = set(recipe_map)
    extras = [source for source in sources if str(source.get("source_id")) not in used]
    candidates = panel_label_sequence(12, mode)
    used_labels = {str(row.get("Метка") or "") for row in rows}
    next_order = max([int(row["Порядок"]) for row in rows] or [0]) + 1
    for source in extras:
        label = next((candidate for candidate in candidates if candidate and candidate not in used_labels), "")
        used_labels.add(label)
        rows.append(_default_row(source, next_order, label, font_size))
        next_order += 1
    return pd.DataFrame(rows, columns=_EDITOR_COLUMNS), missing


def _reconcile_editor(
    sources: list[dict],
    current: pd.DataFrame | None,
    mode: str,
    font_size: float,
    loaded_recipe: dict | None = None,
) -> pd.DataFrame:
    """Preserve manual settings for surviving source IDs when sources change."""
    if not isinstance(current, pd.DataFrame) or current.empty or "_source_id" not in current.columns:
        if loaded_recipe:
            return _editor_from_recipe(sources, loaded_recipe, mode, font_size)[0]
        return _default_editor(sources, mode, font_size)

    existing: dict[str, dict] = {}
    for _, row in current.iterrows():
        source_id = str(row.get("_source_id") or "")
        if source_id and source_id not in existing:
            existing[source_id] = {column: row.get(column) for column in _EDITOR_COLUMNS}
    recipe_map = _recipe_rows(loaded_recipe or {})
    kept: list[dict] = []
    new_sources: list[dict] = []
    for source in sources:
        source_id = str(source.get("source_id") or "")
        if source_id in existing:
            row = dict(existing[source_id])
            row["Источник"] = _source_title(source)
            row["_source_id"] = source_id
            kept.append(row)
        else:
            new_sources.append(source)

    numeric_orders = pd.to_numeric(pd.Series([row.get("Порядок") for row in kept]), errors="coerce") if kept else pd.Series(dtype=float)
    next_order = int(numeric_orders.max()) + 1 if not numeric_orders.empty and numeric_orders.notna().any() else len(kept) + 1
    used_labels = {str(row.get("Метка") or "") for row in kept}
    candidates = panel_label_sequence(12, mode)
    for source in new_sources:
        source_id = str(source.get("source_id") or "")
        settings = recipe_map.get(source_id)
        if settings is not None:
            row = _default_row(source, int(settings["Порядок"]), str(settings["Метка"]), font_size)
            row.update(settings)
        else:
            label = next((candidate for candidate in candidates if candidate and candidate not in used_labels), "")
            used_labels.add(label)
            row = _default_row(source, next_order, label, font_size)
            next_order += 1
        kept.append(row)
    return pd.DataFrame(kept, columns=_EDITOR_COLUMNS)


def _reset_auto_labels(dataframe: pd.DataFrame, mode: str, show_all: bool) -> pd.DataFrame:
    updated = dataframe.copy().reset_index(drop=True)
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
    project_id = int(project["id"])
    try:
        available = project_publication_sources(project_id)
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
        key=f"publication_composer_project_sources_{project_id}",
        placeholder="Фото пород, изображения анализов, шлифы…",
    )
    selected = [by_id[str(value)] for value in selected_ids if str(value) in by_id]
    fallback_notes = [str(item.get("note")) for item in selected if str(item.get("note", "")).strip()]
    if fallback_notes:
        st.warning("\n".join(dict.fromkeys(fallback_notes)))
    return selected


def _restore_recipe(upload, sources: list[dict], mode: str, font_size: float, preset_names: list[str]) -> None:
    if upload is None:
        return
    content = upload.getvalue()
    digest = hashlib.sha256(content).hexdigest()
    if digest == str(st.session_state.get("_publication_composer_applied_recipe", "")):
        return
    recipe = parse_publication_recipe_bytes(content)
    st.session_state["_publication_composer_loaded_recipe"] = recipe
    st.session_state["_publication_composer_applied_recipe"] = digest
    preset_name = str(recipe.get("journal_preset") or "")
    if preset_name in preset_names:
        st.session_state["publication_composer_preset"] = preset_name
    layout = dict(recipe.get("layout") or {})
    st.session_state["publication_composer_columns"] = int(layout.get("columns", 2))
    st.session_state["publication_composer_width"] = float(layout.get("width_in", 7.2))
    st.session_state["publication_composer_panel_height"] = float(layout.get("panel_height_in", 3.2))
    config, missing = _editor_from_recipe(sources, recipe, mode, font_size)
    st.session_state["_publication_composer_config"] = config
    st.session_state["_publication_composer_fingerprint"] = _source_fingerprint(sources)
    st.session_state["_publication_composer_editor_revision"] = int(
        st.session_state.get("_publication_composer_editor_revision", 0)
    ) + 1
    st.session_state["_publication_composer_recipe_missing"] = missing


def render_publication_composer_page() -> None:
    project = active_project()
    render_page_header(
        "Редактор мультипанельных рисунков",
        "Соберите один журнальный рисунок из выбранных изображений. PetroLab автоматически расставит A/B/C или А/Б/В, но каждую метку можно переименовать, выключить и передвинуть.",
        eyebrow="Публикация",
        context=str(project["name"]) if project else "Без проекта",
    )

    render_section_header("Источники панелей", "Можно смешивать готовые графики PetroLab, изображения проекта и новые файлы")
    inbox_sources = _inbox_sources()
    project_sources = _project_source_selector(project)
    uploads = st.file_uploader(
        "Или добавить файлы с компьютера",
        type=_ALLOWED_TYPES,
        accept_multiple_files=True,
        key="publication_composer_uploads",
        help="PNG, JPEG, TIFF и WEBP. Можно добавить уже экспортированные графики PetroLab.",
    )
    sources, duplicate_count = _unique_sources([*inbox_sources, *project_sources, *_upload_sources(uploads)])
    if duplicate_count:
        st.warning(f"Повторяющихся источников пропущено: {duplicate_count}. Одна физическая картинка не дублируется молча.")
    if not sources:
        st.info("Передайте график из PetroLab, выберите изображения из проекта или добавьте файлы с компьютера.")
        return
    if len(sources) > 12:
        st.warning("В одной фигуре сейчас поддерживается до 12 панелей. Используются первые 12 выбранных источников.")
        sources = sources[:12]

    preset_names = list(FIGURE_PRESETS)
    mode_by_title = {title: key for key, title in LABEL_MODE_TITLES.items()}
    current_mode_title = str(st.session_state.get("publication_composer_label_mode", "A, B, C…"))
    label_mode_for_restore = mode_by_title.get(current_mode_title, "latin_upper")
    fallback_preset_name = str(st.session_state.get("publication_composer_preset", "Lithos"))
    fallback_preset = FIGURE_PRESETS.get(fallback_preset_name, next(iter(FIGURE_PRESETS.values())))
    default_label_size_for_restore = max(float(fallback_preset.font_size) + 2.0, 10.0)

    recipe_upload = st.file_uploader(
        "Восстановить настройки из Recipe JSON",
        type=["json"],
        accept_multiple_files=False,
        key="publication_composer_recipe_upload",
        help="Recipe восстанавливает порядок, сетку, размеры и метки. Исходные изображения должны быть доступны в текущих источниках.",
    )
    if recipe_upload is not None:
        try:
            _restore_recipe(recipe_upload, sources, label_mode_for_restore, default_label_size_for_restore, preset_names)
        except Exception as exc:
            st.error(f"Не удалось восстановить recipe: {exc}")

    missing = list(st.session_state.get("_publication_composer_recipe_missing", []))
    if missing:
        still_missing = [source_id for source_id in missing if source_id not in {str(item.get("source_id")) for item in sources}]
        st.session_state["_publication_composer_recipe_missing"] = still_missing
        if still_missing:
            st.warning("В recipe пока недоступны источники: " + ", ".join(still_missing[:8]))

    p1, p2, p3 = st.columns(3)
    preset_name = p1.selectbox(
        "Журнальный preset",
        preset_names,
        index=preset_names.index("Lithos") if "Lithos" in preset_names else 0,
        key="publication_composer_preset",
    )
    preset = FIGURE_PRESETS[preset_name]
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
        loaded_recipe = st.session_state.get("_publication_composer_loaded_recipe")
        loaded_recipe = loaded_recipe if isinstance(loaded_recipe, dict) else None
        st.session_state["_publication_composer_config"] = _reconcile_editor(
            sources,
            st.session_state.get("_publication_composer_config"),
            label_mode,
            default_label_size,
            loaded_recipe,
        )
        st.session_state["_publication_composer_fingerprint"] = fingerprint
        st.session_state["_publication_composer_editor_revision"] = int(
            st.session_state.get("_publication_composer_editor_revision", 0)
        ) + 1

    controls = st.columns([1, 1, 2])
    if controls[0].button("Сбросить метки по схеме", key="publication_reset_labels"):
        current = st.session_state.get("_publication_composer_config")
        if isinstance(current, pd.DataFrame):
            st.session_state["_publication_composer_config"] = _reset_auto_labels(current, label_mode, show_all)
            st.session_state["_publication_composer_editor_revision"] = int(
                st.session_state.get("_publication_composer_editor_revision", 0)
            ) + 1
            st.rerun()
    controls[1].caption("Смена схемы сама по себе не перезаписывает ручные метки.")

    render_section_header("Панели", "Порядок, подписи и положение меток")
    config = st.session_state.get("_publication_composer_config")
    if not isinstance(config, pd.DataFrame) or len(config) != len(sources):
        config = _reconcile_editor(sources, config if isinstance(config, pd.DataFrame) else None, label_mode, default_label_size)
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
