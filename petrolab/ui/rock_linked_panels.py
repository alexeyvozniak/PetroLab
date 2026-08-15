"""Связанная интерактивная мультипанель для whole-rock данных."""
from __future__ import annotations

from io import BytesIO

import pandas as pd
import streamlit as st

from petrolab.io_utils import numeric_candidates
from petrolab.multi_panel_plotting import build_multi_panel_scatter
from petrolab.plotting import figure_png_bytes, figure_svg_bytes
from petrolab.rock_work_groups import (
    ROCK_SELECTION_ID_COLUMN,
    ROCK_WORK_GROUP_COLUMN,
    attach_rock_work_groups,
    clear_rock_work_group,
    list_rock_work_groups,
    set_rock_work_group,
)
from petrolab.ui.linked_panels import render_linked_panel_selection
from petrolab.ui.xy_components import style_dataframe, style_map


def _xlsx_bytes(dataframe: pd.DataFrame) -> bytes:
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dataframe.to_excel(writer, sheet_name="Whole-rock selection", index=False)
    return buffer.getvalue()


def _defaults(numeric: list[str]) -> list[tuple[str, str]]:
    preferred_y = [
        "TiO2", "Al2O3", "FeOt", "MgO", "CaO", "Na2O", "K2O", "P2O5",
        "Nb", "Zr", "Sr", "Rb", "Ba", "Ni", "Cr",
    ]
    pairs: list[tuple[str, str]] = []
    if "SiO2" in numeric:
        pairs.extend(("SiO2", y) for y in preferred_y if y in numeric and y != "SiO2")
    if len(pairs) < 10:
        for index, x in enumerate(numeric):
            if len(pairs) >= 10:
                break
            y = numeric[(index + 1) % len(numeric)] if numeric else x
            if x != y and (x, y) not in pairs:
                pairs.append((x, y))
    return pairs[:10]


def _render_class_actions(selected_ids: list[str], project_id: int) -> None:
    if not selected_ids:
        return
    with st.container(border=True):
        st.markdown("#### Классифицировать текущий whole-rock отбор")
        st.caption(
            "Это рабочий класс PetroLab, а не изменение Lithology/Source. Его можно менять или убрать без потери исходных данных."
        )
        existing = list_rock_work_groups()
        mode = st.selectbox(
            "Рабочий класс",
            ["Новый класс…", *existing],
            key=f"rock_linked_group_mode_{project_id}",
        )
        if mode == "Новый класс…":
            group_name = st.text_input(
                "Название класса",
                placeholder="например, high-Nb, contaminated, group A",
                key=f"rock_linked_group_name_{project_id}",
            ).strip()
        else:
            group_name = str(mode).strip()
        c1, c2 = st.columns(2)
        if c1.button(
            "Присвоить выбранным",
            type="primary",
            width="stretch",
            disabled=not group_name,
            key=f"rock_linked_set_group_{project_id}",
        ):
            try:
                changed = set_rock_work_group(selected_ids, group_name)
            except Exception as exc:
                st.error(f"Рабочий класс не сохранён: {exc}")
            else:
                st.success(f"Класс «{group_name}» присвоен {changed} whole-rock строкам.")
                st.rerun()
        if c2.button(
            "Убрать рабочий класс",
            width="stretch",
            key=f"rock_linked_clear_group_{project_id}",
        ):
            changed = clear_rock_work_group(selected_ids)
            if changed:
                st.success(f"Рабочий класс убран у {changed} строк.")
                st.rerun()


def render_rock_linked_multi_panel(dataframe: pd.DataFrame, project_id: int) -> None:
    """Показать 2–10 связанных whole-rock диаграмм и публикационный дубль тех же панелей."""
    dataframe = attach_rock_work_groups(dataframe)
    numeric = [column for column in numeric_candidates(dataframe) if not str(column).startswith("_")]
    if len(numeric) < 2:
        st.info("Недостаточно числовых whole-rock колонок для мультипанели.")
        return

    st.markdown("### Связанная whole-rock мультипанель")
    st.caption(
        "Клик, рамка и лассо на любой панели заменяют текущий отбор. Те же определения/образцы сразу подсвечиваются на всех остальных панелях."
    )
    defaults = _defaults(numeric)
    c0, c1 = st.columns(2)
    panel_count = c0.slider(
        "Количество графиков",
        2,
        10,
        min(6, max(2, len(defaults))) if defaults else 2,
        key=f"rock_linked_panel_count_{project_id}",
    )
    columns = c1.selectbox(
        "Колонок",
        [1, 2, 3, 4],
        index=1,
        key=f"rock_linked_columns_{project_id}",
    )

    panels: list[dict] = []
    for index in range(panel_count):
        default_x, default_y = defaults[index % len(defaults)] if defaults else (numeric[0], numeric[1])
        with st.expander(f"Панель {index + 1}: {default_y} vs {default_x}", expanded=index < 4):
            a, b, c = st.columns([1, 1, 1.2])
            x = a.selectbox(
                f"X · {index + 1}",
                numeric,
                index=numeric.index(default_x) if default_x in numeric else 0,
                key=f"rock_linked_x_{project_id}_{index}",
            )
            y_options = [column for column in numeric if column != x]
            y_default = default_y if default_y in y_options else y_options[0]
            y = b.selectbox(
                f"Y · {index + 1}",
                y_options,
                index=y_options.index(y_default),
                key=f"rock_linked_y_{project_id}_{index}",
            )
            title = c.text_input(
                f"Название · {index + 1}",
                value=f"{y} vs {x}",
                key=f"rock_linked_title_{project_id}_{index}",
            )
            l1, l2 = st.columns(2)
            log_x = l1.checkbox("log X", key=f"rock_linked_logx_{project_id}_{index}")
            log_y = l2.checkbox("log Y", key=f"rock_linked_logy_{project_id}_{index}")
            panels.append({
                "x": x, "y": y, "x_label": x, "y_label": y,
                "title": title, "log_x": log_x, "log_y": log_y,
            })

    group_candidates = [
        column for column in (
            ROCK_WORK_GROUP_COLUMN, "Источник данных", "Lithology", "Massif", "Locality", "Rock"
        )
        if column in dataframe.columns
    ]
    group_choice = st.selectbox(
        "Группировка",
        ["Без группировки", *group_candidates],
        index=1 if group_candidates else 0,
        key=f"rock_linked_group_column_{project_id}",
    )
    group_column = None if group_choice == "Без группировки" else group_choice

    selected = render_linked_panel_selection(
        dataframe,
        panels,
        id_column=ROCK_SELECTION_ID_COLUMN,
        key=f"rock_multi_{project_id}",
        group_column=group_column,
        columns=int(columns),
    )
    _render_class_actions(selected, project_id)

    with st.expander("Публикационный вид этих же панелей", expanded=False):
        styles: dict = {}
        if group_column and group_column in dataframe.columns:
            groups = sorted(
                dataframe[group_column].astype("string").fillna("Без группы").replace("", "Без группы").unique().tolist()
            )
            editor = st.data_editor(
                style_dataframe([str(value) for value in groups]),
                width="stretch",
                hide_index=True,
                key=f"rock_linked_styles_{project_id}_{group_column}",
            )
            styles = style_map(editor)
        try:
            figure = build_multi_panel_scatter(
                dataframe,
                panels,
                group_column=group_column,
                style_map=styles,
                columns=int(columns),
                width_in=8.0,
                panel_height_in=3.0,
                font_family="Arial",
                font_size=9.0,
                tick_size=8.0,
                marker_size=42.0,
                show_legend=True,
                grid=False,
            )
        except Exception as exc:
            st.error(f"Публикационную whole-rock мультипанель не удалось построить: {exc}")
            return
        st.pyplot(figure, width="stretch")
        e1, e2, e3 = st.columns(3)
        e1.download_button(
            "SVG", figure_svg_bytes(figure), file_name="petrolab_whole_rock_multi_panel.svg",
            mime="image/svg+xml", width="stretch", key=f"rock_linked_svg_{project_id}",
        )
        e2.download_button(
            "PNG 600 dpi", figure_png_bytes(figure, 600), file_name="petrolab_whole_rock_multi_panel.png",
            mime="image/png", width="stretch", key=f"rock_linked_png_{project_id}",
        )
        visible = [column for column in dataframe.columns if not str(column).startswith("_")]
        e3.download_button(
            "XLSX", _xlsx_bytes(dataframe[visible]), file_name="petrolab_whole_rock_multi_panel.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            width="stretch", key=f"rock_linked_xlsx_{project_id}",
        )
