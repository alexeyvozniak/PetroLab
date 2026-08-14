from __future__ import annotations

import streamlit as st

from petrolab.extended_plotting import NORMALIZATION_REFERENCES
from petrolab.settings_service import load_settings, save_settings
from petrolab.ui.layout import render_hint, render_page_header
from petrolab.visualization_presets import FIGURE_PRESETS, POINT_STYLE_PRESETS, TABLE_PRESETS


def _index(options, value, fallback=0):
    return options.index(value) if value in options else fallback


def render_settings_page() -> None:
    render_page_header(
        "Настройки",
        "Локальные настройки интерфейса, рисунков и анализа. Они не изменяют исходные Excel.",
        eyebrow="Система",
    )
    settings = load_settings()
    interface_tab, figures_tab, tables_tab, analysis_tab = st.tabs(["Интерфейс", "Рисунки", "Таблицы", "Анализ"])

    with interface_tab:
        density_labels = {"Комфортная": "comfortable", "Компактная": "compact"}
        current_density = str(settings.get("ui_density", "comfortable"))
        density_label = st.segmented_control(
            "Плотность интерфейса", list(density_labels),
            default="Компактная" if current_density == "compact" else "Комфортная",
        )
        show_help = st.checkbox("Показывать поясняющие подсказки", value=bool(settings.get("show_help_hints", True)))
        show_updates = st.checkbox("Показывать «Что нового» на главной", value=bool(settings.get("show_release_notes_on_home", True)))
        check_updates = st.checkbox(
            "Проверять наличие новой версии", value=bool(settings.get("check_updates_automatically", True)),
            help="Раз в несколько часов ПетроЛаб запрашивает у GitHub только номер публичной версии. Данные проектов, Excel и изображения не передаются.",
        )
        render_hint("Компактный режим уменьшает отступы, но не размер текста и элементов управления.")

    with figures_tab:
        figure_options = list(FIGURE_PRESETS)
        point_options = list(POINT_STYLE_PRESETS)
        figure = st.selectbox(
            "Шаблон рисунка по умолчанию", figure_options,
            index=_index(figure_options, settings.get("default_figure_preset", "Lithos")),
        )
        point = st.selectbox(
            "Стиль точек по умолчанию", point_options,
            format_func=lambda key: POINT_STYLE_PRESETS[key].title,
            index=_index(point_options, settings.get("default_point_style", "balanced")),
        )
        preview = POINT_STYLE_PRESETS[point]
        render_hint("Маркеры: " + "  ".join(preview.markers[:8]))

    with tables_tab:
        table_options = list(TABLE_PRESETS)
        table = st.selectbox(
            "Шаблон таблицы по умолчанию", table_options,
            index=_index(table_options, settings.get("default_table_preset", "Lithos")),
        )
        render_hint("Шаблон задаёт стартовое оформление, но не удаляет научные колонки.")

    with analysis_tab:
        references = list(NORMALIZATION_REFERENCES)
        ree_ref = st.selectbox(
            "Нормировка REE по умолчанию", references,
            index=_index(references, settings.get("default_ree_reference", references[1]), 1),
        )
        outlier_options = ["MAD", "IQR", "NONE"]
        outlier_labels = {"MAD": "MAD — робастный z-score", "IQR": "IQR — правило Тьюки", "NONE": "Не искать автоматически"}
        outlier = st.selectbox(
            "Поиск выбросов по умолчанию", outlier_options,
            index=_index(outlier_options, settings.get("default_outlier_method", "MAD")),
            format_func=lambda value: outlier_labels[value],
        )
        render_hint("Автоматический поиск выбросов только отмечает точки и не удаляет данные.")

    st.divider()
    if st.button("Сохранить настройки", type="primary"):
        save_settings({
            "default_figure_preset": figure,
            "default_table_preset": table,
            "default_point_style": point,
            "ui_density": density_labels.get(density_label or "Комфортная", "comfortable"),
            "show_help_hints": show_help,
            "show_release_notes_on_home": show_updates,
            "check_updates_automatically": check_updates,
            "default_ree_reference": ree_ref,
            "default_outlier_method": outlier,
        })
        st.success("Настройки сохранены.")
        st.rerun()
