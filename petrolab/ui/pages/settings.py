from __future__ import annotations

import streamlit as st

from petrolab.extended_plotting import NORMALIZATION_REFERENCES
from petrolab.settings_service import load_settings, save_settings
from petrolab.visualization_presets import FIGURE_PRESETS, POINT_STYLE_PRESETS, TABLE_PRESETS


def render_settings_page() -> None:
    st.title("Настройки")
    st.write("Настройки хранятся локально рядом с базой ПетроЛаба и не попадают в GitHub или исходные Excel.")
    settings = load_settings()
    with st.form("petrolab_settings"):
        st.subheader("Оформление по умолчанию")
        c1, c2, c3 = st.columns(3)
        figure = c1.selectbox(
            "Рисунки",
            list(FIGURE_PRESETS),
            index=list(FIGURE_PRESETS).index(settings.get("default_figure_preset", "Lithos")) if settings.get("default_figure_preset") in FIGURE_PRESETS else 0,
        )
        table = c2.selectbox(
            "Таблицы",
            list(TABLE_PRESETS),
            index=list(TABLE_PRESETS).index(settings.get("default_table_preset", "Lithos")) if settings.get("default_table_preset") in TABLE_PRESETS else 0,
        )
        point = c3.selectbox(
            "Точки",
            list(POINT_STYLE_PRESETS),
            format_func=lambda key: POINT_STYLE_PRESETS[key].title,
            index=list(POINT_STYLE_PRESETS).index(settings.get("default_point_style", "balanced")) if settings.get("default_point_style") in POINT_STYLE_PRESETS else 0,
        )
        density = st.segmented_control(
            "Плотность интерфейса",
            ["comfortable", "compact"],
            default=settings.get("ui_density", "comfortable"),
        )
        show_help = st.checkbox("Показывать поясняющие подсказки", value=bool(settings.get("show_help_hints", True)))
        show_updates = st.checkbox("Показывать последние изменения на главной", value=bool(settings.get("show_release_notes_on_home", True)))
        ree_ref = st.selectbox(
            "Нормировка REE по умолчанию",
            list(NORMALIZATION_REFERENCES),
            index=list(NORMALIZATION_REFERENCES).index(settings.get("default_ree_reference", list(NORMALIZATION_REFERENCES)[1])) if settings.get("default_ree_reference") in NORMALIZATION_REFERENCES else 1,
        )
        outlier = st.selectbox("Автоматический поиск выбросов", ["MAD", "IQR", "NONE"], index=["MAD", "IQR", "NONE"].index(settings.get("default_outlier_method", "MAD")))
        if st.form_submit_button("Сохранить настройки", type="primary"):
            save_settings({
                "default_figure_preset": figure,
                "default_table_preset": table,
                "default_point_style": point,
                "ui_density": density,
                "show_help_hints": show_help,
                "show_release_notes_on_home": show_updates,
                "default_ree_reference": ree_ref,
                "default_outlier_method": outlier,
            })
            st.success("Настройки сохранены. Обновите страницу, если меняли плотность интерфейса.")

    st.subheader("Что именно делает preset")
    st.markdown(
        "- **Preset рисунка** задаёт стартовые размеры, шрифт, толщины, размер маркеров и DPI. Всё можно изменить перед экспортом.\n"
        "- **Preset точек** задаёт гармоничную последовательность форм и заливки. Он не переименовывает группы.\n"
        "- **Preset таблицы** задаёт шрифт, округление и ориентацию страницы. Он не удаляет колонки автоматически."
    )
