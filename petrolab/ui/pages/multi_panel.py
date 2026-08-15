from __future__ import annotations

from io import BytesIO

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN, attach_work_groups, list_work_groups, set_work_group
from petrolab.composite_points import composite_points_dataframe
from petrolab.dataframe_utils import apply_quick_filter, dataset_label
from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.generations import assign_generation, attach_generations
from petrolab.io_utils import numeric_candidates
from petrolab.measurement_registry import list_entities
from petrolab.multi_panel_plotting import build_multi_panel_scatter
from petrolab.plotting import figure_png_bytes, figure_svg_bytes
from petrolab.source_registry import SOURCE_LABEL_COLUMN, attach_study_metadata
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.linked_panels import render_linked_panel_selection
from petrolab.ui.project_context import active_project
from petrolab.ui.source_controls import render_source_visibility_controls
from petrolab.ui.xy_components import style_dataframe, style_map
from petrolab.visualization_presets import FIGURE_PRESETS


def _xlsx_bytes(dataframe: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="Selected data", index=False)
    return buffer.getvalue()


def _panel_defaults(numeric: list[str]) -> list[tuple[str, str]]:
    preferred = [
        ("Al2O3", "TiO2"), ("Mg#", "TiO2"), ("MgO", "FeOt"),
        ("Nb", "Ta"), ("Rb", "Sr"), ("Ni", "Cr"),
    ]
    pairs = [(x, y) for x, y in preferred if x in numeric and y in numeric]
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


def _raw_dataframe(project_id: int) -> tuple[pd.DataFrame, list[int]]:
    datasets = list_accessible_datasets(project_id)
    labels = {dataset_label(item): int(item["id"]) for item in datasets}
    requested = [int(value) for value in st.session_state.pop("workflow_plot_dataset_ids", [])]
    defaults = [label for label, dataset_id in labels.items() if dataset_id in requested] or list(labels)
    selected_labels = st.multiselect(
        "Наборы",
        list(labels),
        default=defaults,
        key="multi_panel_datasets",
    )
    selected_ids = [labels[label] for label in selected_labels]
    if not selected_ids:
        return pd.DataFrame(), []
    dataframe = attach_study_metadata(
        attach_generations(
            attach_work_groups(load_unified_with_derived(project_id, selected_ids))
        )
    )
    minerals = sorted(dataframe.get("Минерал", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
    if minerals:
        chosen = st.multiselect("Минералы", minerals, default=minerals, key="multi_panel_minerals")
        dataframe = dataframe[dataframe["Минерал"].astype(str).isin(chosen)] if chosen else dataframe.iloc[0:0]
    query = st.text_input(
        "Фильтр",
        placeholder="Sample, Generation, статья, группа…",
        key="multi_panel_query",
    )
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
        "Шлиф",
        ids,
        index=default,
        format_func=lambda value: str(by_id[int(value)]["name"]),
        key="multi_panel_section",
    )
    dataframe = composite_points_dataframe(project_id, thin_section_id=int(section_id))
    if dataframe.empty:
        st.info("На этом шлифе пока нет composite-точек с привязанными анализами.")
        return dataframe, []
    query = st.text_input(
        "Фильтр composite-точек",
        placeholder="P-13, Sample, mineral…",
        key="multi_panel_composite_query",
    )
    dataframe = apply_quick_filter(dataframe, query)
    return dataframe, []


def _render_selection_actions(selected_ids: list[str], project_id: int) -> None:
    """Дать текущему связанному отбору научно явный следующий шаг."""
    if not selected_ids:
        return
    with st.container(border=True):
        st.markdown("#### Что сделать с текущим выделением")
        st.caption(
            "Рабочая группа остаётся обратимой гипотезой. Generation — уже интерпретация; "
            "она пишется отдельно от исходной Generation и сохраняет историю изменений."
        )
        c1, c2 = st.columns(2)
        existing = list_work_groups()
        group_name = c1.text_input(
            "Рабочая группа",
            placeholder="например, N-LF candidate или выбросы Ti",
            key=f"multi_linked_group_name_{project_id}",
        ).strip()
        if c1.button(
            "Сохранить как рабочую группу",
            width="stretch",
            disabled=not group_name,
            key=f"multi_linked_save_group_{project_id}",
        ):
            try:
                count = set_work_group(selected_ids, group_name)
            except Exception as exc:
                st.error(f"Рабочую группу не удалось сохранить: {exc}")
            else:
                st.success(f"Рабочая группа «{group_name}» сохранена для {count} анализов.")
                st.rerun()

        generation_name = c2.text_input(
            "Generation",
            placeholder="например, N-LF, core-1, rim-2",
            key=f"multi_linked_generation_name_{project_id}",
        ).strip()
        rationale = c2.text_input(
            "Основание (необязательно)",
            placeholder="Ti–Al + Mg# + текстурная зона",
            key=f"multi_linked_generation_rationale_{project_id}",
        ).strip()
        if c2.button(
            "Утвердить как Generation",
            type="primary",
            width="stretch",
            disabled=not generation_name,
            key=f"multi_linked_save_generation_{project_id}",
        ):
            try:
                count = assign_generation(
                    selected_ids,
                    generation_name,
                    rationale=rationale,
                    source_kind="linked_multi_panel",
                    source_value=group_name if group_name in existing else "interactive selection",
                )
            except Exception as exc:
                st.error(f"Generation не удалось сохранить: {exc}")
            else:
                st.success(f"Generation «{generation_name}» утверждена для {count} анализов.")
                st.rerun()


def render_multi_panel_page() -> None:
    project = active_project()
    render_page_header(
        "Несколько графиков сразу",
        "Одна выборка и до десяти связанных диаграмм. Клик, рамка или лассо могут выделить точки на одной панели и подсветить те же анализы на всех остальных.",
        eyebrow="Сравнение",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала выберите проект.")
        return
    project_id = int(project["id"])

    requested_mode = st.session_state.pop("multi_panel_data_mode", None)
    modes = ["Обычные анализы", "Физические точки EDS + LA"]
    if requested_mode in modes:
        st.session_state["multi_panel_mode"] = requested_mode
    mode = st.segmented_control(
        "Строка на графике",
        modes,
        default=st.session_state.get("multi_panel_mode", modes[0]),
        key="multi_panel_mode",
    ) or modes[0]

    if mode == "Физические точки EDS + LA":
        dataframe, selected_ids = _composite_dataframe(project_id)
    else:
        dataframe, selected_ids = _raw_dataframe(project_id)
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

    render_section_header("Панели", "Выберите от двух до десяти пар осей")
    defaults = _panel_defaults(numeric)
    panel_count = st.slider(
        "Количество графиков",
        2,
        10,
        min(4, max(2, len(defaults))) if defaults else 2,
        key="multi_panel_count",
    )
    panels: list[dict] = []
    for index in range(panel_count):
        default_x, default_y = defaults[index % len(defaults)] if defaults else (numeric[0], numeric[1])
        with st.container(border=True):
            c1, c2, c3 = st.columns([1, 1, 1.2])
            x = c1.selectbox(
                f"X · {index + 1}",
                numeric,
                index=numeric.index(default_x) if default_x in numeric else 0,
                key=f"multi_x_{index}",
            )
            y_options = [column for column in numeric if column != x]
            y_default = default_y if default_y in y_options else y_options[0]
            y = c2.selectbox(
                f"Y · {index + 1}",
                y_options,
                index=y_options.index(y_default),
                key=f"multi_y_{index}",
            )
            title = c3.text_input(
                f"Название · {index + 1}",
                value=f"{y} vs {x}",
                key=f"multi_title_{index}",
            )
            l1, l2 = st.columns(2)
            log_x = l1.checkbox("log X", key=f"multi_log_x_{index}")
            log_y = l2.checkbox("log Y", key=f"multi_log_y_{index}")
            panels.append({
                "x": x,
                "y": y,
                "x_label": x,
                "y_label": y,
                "title": title,
                "log_x": log_x,
                "log_y": log_y,
            })

    categorical = [
        column for column in dataframe.columns
        if not str(column).startswith("_")
        and column not in numeric
        and dataframe[column].nunique(dropna=True) <= 100
    ]
    preferred = [
        column for column in [SOURCE_LABEL_COLUMN, "Источник", WORK_GROUP_COLUMN, "PetroLab Generation", "Generation", "Textural zone", "Sample", "Набор", "Минерал", "Physical Point"]
        if column in categorical
    ]
    group_options = ["Без группировки", *preferred, *[column for column in categorical if column not in preferred]]
    suggested = SOURCE_LABEL_COLUMN if SOURCE_LABEL_COLUMN in preferred else ("Источник" if "Источник" in preferred else (preferred[0] if preferred else "Без группировки"))
    group = st.selectbox(
        "Общая группировка всех панелей",
        group_options,
        index=group_options.index(suggested),
        key="multi_panel_group",
    )
    group_col = None if group == "Без группировки" else group
    styles: dict = {}
    if group_col:
        groups = sorted(dataframe[group_col].astype("string").fillna("Без группы").replace("", "Без группы").unique().tolist())
        with st.expander("Стили серий · общие для всех графиков", expanded=True):
            st.caption("Для литературной серии можно уменьшить Alpha или переключить «Показывать» на «Поле» / «Точки + поле». Поле строится как confidence ellipse, convex hull или KDE.")
            editor = st.data_editor(
                style_dataframe([str(value) for value in groups]),
                width="stretch",
                hide_index=True,
                column_config={
                    "Маркер": st.column_config.SelectboxColumn("Маркер"),
                    "Alpha": st.column_config.NumberColumn("Alpha", min_value=0.05, max_value=1.0, step=0.05),
                    "Alpha поля": st.column_config.NumberColumn("Alpha поля", min_value=0.0, max_value=1.0, step=0.05),
                    "Показывать": st.column_config.SelectboxColumn("Показывать", options=["Точки", "Поле", "Точки + поле", "Только центр"]),
                    "Поле": st.column_config.SelectboxColumn("Поле", options=["Confidence ellipse", "Convex hull", "KDE 90%"]),
                },
                key=f"multi_panel_styles_{group_col}",
            )
            styles = style_map(editor)

    preset_names = list(FIGURE_PRESETS)
    preset_name = st.selectbox(
        "Журнальный preset",
        preset_names,
        index=preset_names.index("Lithos") if "Lithos" in preset_names else 0,
        key="multi_panel_preset",
    )
    preset = FIGURE_PRESETS[preset_name]
    c1, c2, c3 = st.columns(3)
    columns = c1.selectbox("Колонок в фигуре", [1, 2, 3, 4], index=1, key="multi_panel_columns")
    marker_size = c2.slider("Размер точек", 10, 160, int(round(preset.marker_size)), 2, key="multi_panel_marker")
    grid = c3.checkbox("Сетка", value=preset.grid, key="multi_panel_grid")

    if mode == "Обычные анализы" and "_analysis_id" in dataframe.columns:
        render_section_header(
            "Интерактивная связанная мультипанель",
            "Клик, рамка и лассо работают как один общий отбор по analysis_id",
        )
        linked_ids = render_linked_panel_selection(
            dataframe,
            panels,
            id_column="_analysis_id",
            key=f"mineral_multi_{project_id}",
            group_column=group_col,
            columns=int(columns),
        )
        _render_selection_actions(linked_ids, project_id)
    elif mode == "Физические точки EDS + LA":
        st.caption("Для composite-точек интерактивный связанный отбор пока не присваивает Generation автоматически: сначала нужно выбрать физическую точку/анализ явно.")

    render_section_header("Публикационный вид", "Те же 2–10 панелей в стабильном SVG/PNG")
    try:
        figure = build_multi_panel_scatter(
            dataframe,
            panels,
            group_column=group_col,
            style_map=styles,
            columns=int(columns),
            width_in=max(preset.width_in, 7.2),
            panel_height_in=max(2.8, preset.height_in * 0.62),
            font_family=preset.font_family,
            font_size=preset.font_size,
            tick_size=preset.tick_size,
            spine_width=preset.spine_width,
            marker_size=float(marker_size),
            show_legend=True,
            grid=bool(grid),
        )
    except Exception as exc:
        st.error(f"Не удалось построить multi-panel: {exc}")
        return

    st.pyplot(figure, width="stretch")
    render_section_header("Экспорт", "Одна фигура и точная таблица текущего отбора")
    e1, e2, e3 = st.columns(3)
    e1.download_button(
        "SVG",
        figure_svg_bytes(figure),
        file_name="petrolab_multi_panel.svg",
        mime="image/svg+xml",
        width="stretch",
    )
    e2.download_button(
        "PNG 600 dpi",
        figure_png_bytes(figure, 600),
        file_name="petrolab_multi_panel.png",
        mime="image/png",
        width="stretch",
    )
    visible_columns = [column for column in dataframe.columns if not str(column).startswith("_")]
    e3.download_button(
        "XLSX данных",
        _xlsx_bytes(dataframe[visible_columns]),
        file_name="petrolab_multi_panel_data.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )
    st.caption(
        f"{preset.title} · {preset.font_family} · общая выборка и стили для {len(panels)} панелей."
    )
    plt.close(figure)
