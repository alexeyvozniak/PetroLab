from __future__ import annotations

from io import BytesIO

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, attach_work_groups
from petrolab.composite_points import composite_points_dataframe
from petrolab.dataframe_utils import apply_quick_filter, dataset_label
from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.generations import attach_generations
from petrolab.io_utils import numeric_candidates
from petrolab.measurement_registry import list_entities
from petrolab.multi_panel_plotting import build_multi_panel_scatter
from petrolab.plotting import figure_png_bytes, figure_svg_bytes
from petrolab.source_registry import SOURCE_LABEL_COLUMN, attach_study_metadata
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.linked_panels import render_linked_panel_selection
from petrolab.ui.plot_spec import PlotSpec, clear_multi_panel_inbox, peek_multi_panel_inbox
from petrolab.ui.project_context import active_project
from petrolab.ui.selection_components import render_selection_panel
from petrolab.ui.source_controls import render_source_visibility_controls
from petrolab.ui.xy_components import style_dataframe, style_map
from petrolab.visualization_presets import FIGURE_PRESETS


_CURATED_GROUPS = (
    "PetroLab Generation", "Generation", WORK_GROUP_COLUMN, "Sample", "Grain", "Textural zone",
    SOURCE_LABEL_COLUMN, "Источник", "Набор", "Минерал", "Physical Point",
)


def _xlsx_bytes(dataframe: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="Selected data", index=False)
    return buffer.getvalue()


def _panel_defaults(numeric: list[str], inbox: PlotSpec | None = None) -> list[tuple[str, str]]:
    preferred = [
        ("Al2O3", "TiO2"), ("Mg#", "TiO2"), ("MgO", "FeOt"),
        ("Nb", "Ta"), ("Rb", "Sr"), ("Ni", "Cr"),
    ]
    pairs: list[tuple[str, str]] = []
    if inbox is not None and inbox.x in numeric and inbox.y in numeric and inbox.x != inbox.y:
        pairs.append((inbox.x, inbox.y))
    pairs.extend((x, y) for x, y in preferred if x in numeric and y in numeric and (x, y) not in pairs)
    if not pairs and len(numeric) >= 2:
        pairs = [(numeric[0], numeric[1])]
    if len(numeric) >= 2:
        cursor = 0
        attempts = 0
        while len(pairs) < 10 and attempts < max(20, len(numeric) * len(numeric)):
            x = numeric[cursor % len(numeric)]
            y = numeric[(cursor + 1 + cursor // max(1, len(numeric))) % len(numeric)]
            cursor += 1
            attempts += 1
            if x != y and (x, y) not in pairs:
                pairs.append((x, y))
    return pairs[:10]


def _raw_dataframe(project_id: int, inbox: PlotSpec | None) -> tuple[pd.DataFrame, list[int]]:
    datasets = list_accessible_datasets(project_id)
    labels = {dataset_label(item): int(item["id"]) for item in datasets}
    requested = list(inbox.dataset_ids) if inbox is not None else [int(value) for value in st.session_state.pop("workflow_plot_dataset_ids", [])]
    defaults = [label for label, dataset_id in labels.items() if dataset_id in requested] or list(labels)
    if inbox is not None:
        st.session_state.pop("multi_panel_datasets", None)
    selected_labels = st.multiselect(
        "Наборы", list(labels), default=defaults, key="multi_panel_datasets",
    )
    selected_ids = [labels[label] for label in selected_labels]
    if not selected_ids:
        return pd.DataFrame(), []
    dataframe = attach_study_metadata(
        attach_generations(
            attach_work_groups(load_unified_with_derived(project_id, selected_ids))
        )
    )
    if inbox is not None and inbox.analysis_ids and "_analysis_id" in dataframe.columns:
        exact = set(inbox.analysis_ids)
        dataframe = dataframe[dataframe["_analysis_id"].astype(str).isin(exact)].copy()
        st.caption(f"Перенесён точный состав исходного XY: {len(dataframe)} анализов.")
    minerals = sorted(dataframe.get("Минерал", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
    if minerals:
        chosen = st.multiselect("Минералы", minerals, default=minerals, key="multi_panel_minerals")
        dataframe = dataframe[dataframe["Минерал"].astype(str).isin(chosen)] if chosen else dataframe.iloc[0:0]
    query = st.text_input("Фильтр", placeholder="Sample, Generation, статья, группа…", key="multi_panel_query")
    dataframe = apply_quick_filter(dataframe, query)
    if not dataframe.empty:
        dataframe, _, _, _ = render_source_visibility_controls(dataframe, key="multi_panel_sources")
    return dataframe, selected_ids


def _composite_dataframe(project_id: int) -> tuple[pd.DataFrame, list[int]]:
    sections = [item for item in list_entities(project_id) if item["kind"] == "thin_section"]
    if not sections:
        st.info("Нет шлифов с физическими точками.")
        return pd.DataFrame(), []
    by_id = {int(item["id"]): item for item in sections}
    pending = st.session_state.pop("multi_panel_thin_section_id", None)
    ids = list(by_id)
    default = ids.index(int(pending)) if pending is not None and int(pending) in by_id else 0
    section_id = st.selectbox(
        "Шлиф", ids, index=default,
        format_func=lambda value: str(by_id[int(value)]["name"]), key="multi_panel_section",
    )
    dataframe = composite_points_dataframe(project_id, thin_section_id=int(section_id))
    if dataframe.empty:
        st.info("На этом шлифе пока нет composite-точек с привязанными анализами.")
        return dataframe, []
    query = st.text_input("Фильтр composite-точек", placeholder="P-13, Sample, mineral…", key="multi_panel_composite_query")
    dataframe = apply_quick_filter(dataframe, query)
    return dataframe, []


def _prepare_inbox_widgets(inbox: PlotSpec | None, numeric: list[str]) -> None:
    if inbox is None or inbox.x not in numeric or inbox.y not in numeric:
        return
    token = f"{inbox.x}|{inbox.y}|{inbox.group_column}|{len(inbox.analysis_ids)}|{inbox.title}"
    if st.session_state.get("_multi_panel_inbox_applied") == token:
        return
    st.session_state["multi_panel_count"] = max(2, int(st.session_state.get("multi_panel_count", 2) or 2))
    st.session_state["multi_x_0"] = inbox.x
    st.session_state["multi_y_0"] = inbox.y
    st.session_state["multi_title_0"] = inbox.title or f"{inbox.y} vs {inbox.x}"
    st.session_state["multi_log_x_0"] = bool(inbox.log_x)
    st.session_state["multi_log_y_0"] = bool(inbox.log_y)
    st.session_state["_multi_panel_inbox_applied"] = token


def _group_control(dataframe: pd.DataFrame, numeric: list[str], inbox: PlotSpec | None) -> str | None:
    categorical = [
        column for column in dataframe.columns
        if not str(column).startswith("_") and column not in numeric and dataframe[column].nunique(dropna=True) <= 100
    ]
    curated = [column for column in _CURATED_GROUPS if column in categorical]
    options = ["Без группировки", *curated]
    advanced = [column for column in categorical if column not in curated]
    if advanced:
        options.append("Другой столбец…")
    desired = inbox.group_column if inbox is not None and inbox.group_column in curated else None
    if desired and st.session_state.get("multi_panel_group") not in options:
        st.session_state["multi_panel_group"] = desired
    suggested = desired or (SOURCE_LABEL_COLUMN if SOURCE_LABEL_COLUMN in curated else (curated[0] if curated else "Без группировки"))
    group = st.selectbox(
        "Общая группировка всех панелей", options,
        index=options.index(suggested) if suggested in options else 0,
        key="multi_panel_group",
    )
    if group == "Другой столбец…":
        group = st.selectbox("Другой столбец", advanced, key="multi_panel_group_advanced") if advanced else "Без группировки"
    return None if group == "Без группировки" else str(group)


def _ordered_panels(panels: list[dict]) -> list[dict]:
    if len(panels) <= 1:
        return panels
    order = pd.DataFrame({
        "Панель": [panel.get("title") or f"Панель {index + 1}" for index, panel in enumerate(panels)],
        "Позиция": list(range(1, len(panels) + 1)),
    })
    edited = st.data_editor(
        order, hide_index=True, width="stretch",
        disabled=["Панель"],
        column_config={"Позиция": st.column_config.NumberColumn("Позиция", min_value=1, max_value=len(panels), step=1)},
        key="multi_panel_order",
    )
    positions = pd.to_numeric(edited["Позиция"], errors="coerce")
    if positions.isna().any() or positions.duplicated().any():
        st.warning("Позиции панелей должны быть уникальными числами. Пока используется исходный порядок.")
        return panels
    indices = sorted(range(len(panels)), key=lambda index: float(positions.iloc[index]))
    return [panels[index] for index in indices]


def render_multi_panel_page() -> None:
    project = active_project()
    render_page_header(
        "Сравнить на нескольких диаграммах",
        "Одна выборка, единый linked selection и 2–10 XY-панелей. Готовый одиночный график можно передать сюда без повторной настройки.",
        eyebrow="Исследование",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала выберите проект.")
        return
    project_id = int(project["id"])
    inbox = peek_multi_panel_inbox()
    if inbox is not None:
        st.success("Первый график перенесён из XY вместе с данными, осями и группировкой.")

    requested_mode = st.session_state.pop("multi_panel_data_mode", None)
    modes = ["Обычные анализы", "Физические точки EDS + LA"]
    if inbox is not None:
        requested_mode = "Обычные анализы"
    if requested_mode in modes:
        st.session_state["multi_panel_mode"] = requested_mode
    mode = st.segmented_control(
        "Строка на графике", modes,
        default=st.session_state.get("multi_panel_mode", modes[0]), key="multi_panel_mode",
    ) or modes[0]

    if mode == "Физические точки EDS + LA":
        dataframe, selected_dataset_ids = _composite_dataframe(project_id)
        inbox = None
    else:
        dataframe, selected_dataset_ids = _raw_dataframe(project_id, inbox)
    if dataframe.empty:
        return

    numeric = numeric_candidates(dataframe)
    if len(numeric) < 2:
        st.info("В текущем отборе недостаточно числовых колонок для XY-диаграмм.")
        return
    render_badges([
        (f"строк · {len(dataframe)}", "accent"),
        (f"числовых полей · {len(numeric)}", "neutral"),
        ("composite" if mode != "Обычные анализы" else "analysis rows", "success" if mode != "Обычные анализы" else "neutral"),
    ])

    _prepare_inbox_widgets(inbox, numeric)
    render_section_header("Панели", "Добавляйте оси и меняйте порядок без повторного выбора исходных данных")
    defaults = _panel_defaults(numeric, inbox)
    panel_count = st.slider(
        "Количество графиков", 2, 10,
        min(4, max(2, len(defaults))) if "multi_panel_count" not in st.session_state else int(st.session_state["multi_panel_count"]),
        key="multi_panel_count",
    )
    panels: list[dict] = []
    for index in range(panel_count):
        default_x, default_y = defaults[index % len(defaults)] if defaults else (numeric[0], numeric[1])
        with st.container(border=True):
            st.markdown(f"**Панель {index + 1}**")
            c1, c2, c3 = st.columns([1, 1, 1.2])
            x = c1.selectbox(
                "X", numeric, index=numeric.index(default_x) if default_x in numeric else 0,
                key=f"multi_x_{index}",
            )
            y_options = [column for column in numeric if column != x]
            y_default = default_y if default_y in y_options else y_options[0]
            y = c2.selectbox(
                "Y", y_options, index=y_options.index(y_default), key=f"multi_y_{index}",
            )
            default_title = inbox.title if index == 0 and inbox is not None and inbox.title else f"{y} vs {x}"
            title = c3.text_input("Название", value=default_title, key=f"multi_title_{index}")
            l1, l2 = st.columns(2)
            log_x = l1.checkbox("log X", value=bool(inbox.log_x) if index == 0 and inbox is not None else False, key=f"multi_log_x_{index}")
            log_y = l2.checkbox("log Y", value=bool(inbox.log_y) if index == 0 and inbox is not None else False, key=f"multi_log_y_{index}")
            panels.append({"x": x, "y": y, "x_label": x, "y_label": y, "title": title, "log_x": log_x, "log_y": log_y})
    panels = _ordered_panels(panels)

    group_col = _group_control(dataframe, numeric, inbox)
    styles: dict = {}
    if group_col:
        groups = sorted(dataframe[group_col].astype("string").fillna("Без группы").replace("", "Без группы").unique().tolist())
        existing = inbox.style_map if inbox is not None and inbox.group_column == group_col else {}
        with st.expander("Стили серий · общие для всех графиков", expanded=False):
            editor = st.data_editor(
                style_dataframe([str(value) for value in groups], existing=existing),
                width="stretch", hide_index=True,
                column_config={
                    "Alpha": st.column_config.NumberColumn("Alpha", min_value=0.05, max_value=1.0, step=0.05),
                    "Alpha поля": st.column_config.NumberColumn("Alpha поля", min_value=0.0, max_value=1.0, step=0.05),
                    "Показывать": st.column_config.SelectboxColumn("Показывать", options=["Точки", "Поле", "Точки + поле", "Только центр"]),
                    "Поле": st.column_config.SelectboxColumn("Поле", options=["Confidence ellipse", "Convex hull", "KDE 90%"]),
                }, key=f"multi_panel_styles_{group_col}",
            )
            styles = style_map(editor)

    preset_names = list(FIGURE_PRESETS)
    preset_name = st.selectbox(
        "Журнальный preset", preset_names,
        index=preset_names.index("Lithos") if "Lithos" in preset_names else 0, key="multi_panel_preset",
    )
    preset = FIGURE_PRESETS[preset_name]
    c1, c2, c3 = st.columns(3)
    columns = c1.selectbox("Колонок в фигуре", [1, 2, 3, 4], index=1, key="multi_panel_columns")
    marker_size = c2.slider("Размер точек", 10, 160, int(round(preset.marker_size)), 2, key="multi_panel_marker")
    grid = c3.checkbox("Сетка", value=preset.grid, key="multi_panel_grid")

    if mode == "Обычные анализы" and "_analysis_id" in dataframe.columns:
        render_section_header("Связанное исследование", "Один и тот же Selection работает на всех панелях, в таблице, XY и PCA")
        render_linked_panel_selection(
            dataframe, panels, id_column="_analysis_id", key=f"mineral_multi_{project_id}",
            group_column=group_col, columns=int(columns),
        )
        render_selection_panel(dataframe, project_id=project_id, key_prefix="multi_panel_selection")
    else:
        st.caption("Composite-точки пока исследуются как физические точки; Generation назначается только после явного выбора связанных анализов.")

    if inbox is not None:
        clear_multi_panel_inbox()

    render_section_header("Публикационный вид", "Те же панели в стабильном SVG/PNG; это не редактор A/B/C")
    try:
        figure = build_multi_panel_scatter(
            dataframe, panels, group_column=group_col, style_map=styles,
            columns=int(columns), width_in=max(preset.width_in, 7.2), panel_height_in=max(2.8, preset.height_in * 0.62),
            font_family=preset.font_family, font_size=preset.font_size, tick_size=preset.tick_size,
            spine_width=preset.spine_width, marker_size=float(marker_size), show_legend=True, grid=bool(grid),
        )
    except Exception as exc:
        st.error(f"Не удалось построить multi-panel: {exc}")
        return

    st.pyplot(figure, width="stretch")
    render_section_header("Экспорт", "Одна фигура и точная таблица текущей выборки")
    e1, e2, e3 = st.columns(3)
    e1.download_button("SVG", figure_svg_bytes(figure), file_name="petrolab_multi_panel.svg", mime="image/svg+xml", width="stretch")
    e2.download_button("PNG 600 dpi", figure_png_bytes(figure, 600), file_name="petrolab_multi_panel.png", mime="image/png", width="stretch")
    visible_columns = [column for column in dataframe.columns if not str(column).startswith("_")]
    e3.download_button(
        "XLSX данных", _xlsx_bytes(dataframe[visible_columns]), file_name="petrolab_multi_panel_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch",
    )
    st.caption(f"{preset.title} · {preset.font_family} · общая выборка и стили для {len(panels)} панелей.")
    plt.close(figure)
