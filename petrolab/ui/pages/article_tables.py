from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.article_tables import article_table_xlsx_bytes, format_dataframe_for_article
from petrolab.repositories.rock_repository import composition_wide
from petrolab.ui.data_scope import render_analysis_scope
from petrolab.ui.components import render_project_selector
from petrolab.visualization_presets import TABLE_PRESETS


def _column_selector(dataframe: pd.DataFrame, key: str) -> list[str]:
    meta = [
        column for column in [
            "Project", "Проект", "Rock", "Sample", "Grain", "Point", "Generation",
            "Набор", "Минерал", "Massif", "Lithology", "Age_Ma",
        ]
        if column in dataframe.columns
    ]
    chemistry = [column for column in dataframe.columns if not str(column).startswith("_") and column not in meta]
    ordered = meta + chemistry
    defaults = ordered[: min(24, len(ordered))]
    return st.multiselect("Колонки таблицы", ordered, default=defaults, key=key)


def _render_table(dataframe: pd.DataFrame, key_prefix: str, default_title: str) -> None:
    if dataframe.empty:
        st.info("Нет данных для таблицы.")
        return
    columns = _column_selector(dataframe, f"{key_prefix}_columns")
    if not columns:
        return
    c1, c2 = st.columns(2)
    preset = c1.selectbox("Журнальный preset", list(TABLE_PRESETS), key=f"{key_prefix}_preset")
    title = c2.text_input("Название таблицы", value=default_title, key=f"{key_prefix}_title")
    note = st.text_area("Примечание под таблицей", key=f"{key_prefix}_note", height=80)
    formatted = format_dataframe_for_article(dataframe, preset_name=preset, columns=columns)
    st.dataframe(formatted, width="stretch", height=520, hide_index=True)
    st.caption(TABLE_PRESETS[preset].note or "Preset задаёт шрифт, округление и ориентацию страницы; содержимое колонок остаётся под вашим контролем.")
    data = article_table_xlsx_bytes(formatted, preset_name=preset, title=title, note=note)
    st.download_button(
        "Скачать оформленный XLSX",
        data,
        file_name=f"{key_prefix}_{preset.replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key_prefix}_download",
    )


def render_article_tables_page() -> None:
    st.title("Таблицы для статьи")
    st.write(
        "Конструктор публикационных таблиц с одинаковой логикой для минералов и валовых составов. "
        "Preset отвечает за оформление, а выбор строк и колонок остаётся полностью ручным."
    )
    mode = st.segmented_control("Данные", ["Минеральные анализы", "Валовые составы пород"], default="Минеральные анализы", key="article_table_mode")
    if mode == "Минеральные анализы":
        scope = render_analysis_scope("article_table")
        if scope is None:
            return
        _render_table(scope.dataframe, "mineral_table", "Mineral compositions")
    else:
        project = render_project_selector("article_table_rocks_project")
        if project is None:
            return
        dataframe = composition_wide(int(project["id"]))
        _render_table(dataframe, "rock_table", "Whole-rock compositions")
