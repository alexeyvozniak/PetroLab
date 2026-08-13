from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from petrolab.settings_service import load_settings
from petrolab.visualization_presets import FIGURE_PRESETS, POINT_STYLE_PRESETS


@dataclass(frozen=True)
class FigureStyleSelection:
    preset_name: str
    point_style_name: str
    font_family: str
    font_size: float
    tick_size: float
    label_size: float
    marker_size: float
    line_width: float
    spine_width: float
    width_in: float
    height_in: float
    dpi: int
    grid: bool
    monochrome: bool
    show_legend: bool
    label_points: bool
    point_label_column: str | None


def _ternary_recipe_defaults(key_prefix: str) -> dict:
    if key_prefix != "ternary_style":
        return {}
    recipe = st.session_state.get("loaded_ternary_recipe") or {}
    if not isinstance(recipe, dict):
        return {}
    token = hashlib.sha256(
        json.dumps(recipe, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest() if recipe else ""
    token_key = "_ternary_style_recipe_token"
    if st.session_state.get(token_key) != token:
        for suffix in (
            "figure_preset", "point_style", "font", "font_size", "label_size", "tick_size",
            "marker_size", "line_width", "spine_width", "width", "height", "dpi", "grid",
            "mono", "legend", "label_points", "point_label_col",
        ):
            st.session_state.pop(f"{key_prefix}_{suffix}", None)
        st.session_state[token_key] = token
    return recipe


def render_figure_style_controls(dataframe: pd.DataFrame, *, key_prefix: str, default_preset: str | None = None) -> FigureStyleSelection:
    settings = load_settings()
    recipe = _ternary_recipe_defaults(key_prefix)
    preferred_figure = str(recipe.get("figure_preset") or default_preset or settings.get("default_figure_preset", "Lithos"))
    preferred_points = str(recipe.get("point_style_preset") or settings.get("default_point_style", "balanced"))

    with st.expander("Оформление рисунка", expanded=False):
        st.caption("Журнальный preset — стартовая геометрия и типографика; перед подачей сверяйте актуальные author guidelines.")
        preset_names = list(FIGURE_PRESETS)
        preset_name = st.selectbox(
            "Журнальный preset", preset_names,
            index=preset_names.index(preferred_figure) if preferred_figure in preset_names else 0,
            key=f"{key_prefix}_figure_preset",
        )
        preset = FIGURE_PRESETS[preset_name]
        point_style_names = list(POINT_STYLE_PRESETS)
        point_style_name = st.selectbox(
            "Гармоничный набор маркеров", point_style_names,
            format_func=lambda name: POINT_STYLE_PRESETS[name].title,
            index=point_style_names.index(preferred_points) if preferred_points in point_style_names else 0,
            key=f"{key_prefix}_point_style",
        )
        c1, c2, c3 = st.columns(3)
        font_options = ["Arial", "DejaVu Sans", "Times New Roman"]
        preferred_font = str(recipe.get("font_family") or preset.font_family)
        font_family = c1.selectbox(
            "Шрифт", font_options,
            index=font_options.index(preferred_font) if preferred_font in font_options else 0,
            key=f"{key_prefix}_font",
        )
        font_size = c2.slider("Основной шрифт", 6.0, 18.0, float(recipe.get("font_size", preset.font_size)), 0.5, key=f"{key_prefix}_font_size")
        label_size = c3.slider("Подписи осей", 6.0, 20.0, float(recipe.get("label_size", preset.label_size)), 0.5, key=f"{key_prefix}_label_size")
        c4, c5, c6, c7 = st.columns(4)
        tick_size = c4.slider("Деления", 6.0, 16.0, float(recipe.get("tick_size", preset.tick_size)), 0.5, key=f"{key_prefix}_tick_size")
        marker_size = c5.slider("Размер точки", 10.0, 180.0, float(recipe.get("marker_size", preset.marker_size)), 2.0, key=f"{key_prefix}_marker_size")
        line_width = c6.slider("Толщина линий", 0.4, 3.0, float(recipe.get("line_width", preset.line_width)), 0.1, key=f"{key_prefix}_line_width")
        spine_width = c7.slider("Толщина рамки", 0.4, 3.0, float(recipe.get("spine_width", preset.spine_width)), 0.1, key=f"{key_prefix}_spine_width")
        d1, d2, d3 = st.columns(3)
        width_in = d1.slider("Ширина, inch", 2.5, 12.0, float(recipe.get("width_in", preset.width_in)), 0.1, key=f"{key_prefix}_width")
        height_in = d2.slider("Высота, inch", 2.5, 10.0, float(recipe.get("height_in", preset.height_in)), 0.1, key=f"{key_prefix}_height")
        dpi_values = [300, 450, 600, 900]
        preferred_dpi = int(recipe.get("dpi", preset.dpi))
        dpi = int(d3.selectbox("DPI", dpi_values, index=dpi_values.index(preferred_dpi) if preferred_dpi in dpi_values else 2, key=f"{key_prefix}_dpi"))
        e1, e2, e3 = st.columns(3)
        grid = e1.checkbox("Сетка", value=bool(recipe.get("show_grid", preset.grid)), key=f"{key_prefix}_grid")
        monochrome = e2.checkbox("Ч/б", value=bool(recipe.get("monochrome", preset.monochrome)), key=f"{key_prefix}_mono")
        show_legend = e3.checkbox("Легенда", value=bool(recipe.get("show_legend", True)), key=f"{key_prefix}_legend")
        label_candidates = [column for column in ["Sample", "Grain", "Point", "Generation", "Набор", "Рабочая группа"] if column in dataframe.columns]
        label_points = st.checkbox("Подписывать точки", value=bool(recipe.get("annotate", False)), key=f"{key_prefix}_label_points")
        point_label_column = None
        if label_points and label_candidates:
            saved_label_col = recipe.get("label_col")
            point_label_column = st.selectbox(
                "Колонка для подписи", label_candidates,
                index=label_candidates.index(saved_label_col) if saved_label_col in label_candidates else 0,
                key=f"{key_prefix}_point_label_col",
            )

    return FigureStyleSelection(
        preset_name=preset_name, point_style_name=point_style_name,
        font_family=font_family, font_size=float(font_size), tick_size=float(tick_size),
        label_size=float(label_size), marker_size=float(marker_size), line_width=float(line_width),
        spine_width=float(spine_width), width_in=float(width_in), height_in=float(height_in),
        dpi=dpi, grid=bool(grid), monochrome=bool(monochrome), show_legend=bool(show_legend),
        label_points=bool(label_points), point_label_column=point_label_column,
    )


def render_custom_fields(key_prefix: str) -> pd.DataFrame:
    with st.expander("Пользовательские поля", expanded=False):
        st.caption("Можно добавить прямоугольные области поверх публикационного XY-графика. Они не меняют данные.")
        default = pd.DataFrame(columns=["label", "x_min", "x_max", "y_min", "y_max"])
        edited = st.data_editor(
            default, num_rows="dynamic", width="stretch", hide_index=True,
            key=f"{key_prefix}_custom_fields",
            column_config={
                "label": st.column_config.TextColumn("Подпись"),
                "x_min": st.column_config.NumberColumn("X min"),
                "x_max": st.column_config.NumberColumn("X max"),
                "y_min": st.column_config.NumberColumn("Y min"),
                "y_max": st.column_config.NumberColumn("Y max"),
            },
        )
    return edited
