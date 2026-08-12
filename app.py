from __future__ import annotations

import io
import json

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab import __version__
from petrolab.db import (
    delete_plot_recipe,
    delete_style_profile,
    ensure_storage,
    list_change_log,
    list_datasets,
    list_plot_recipes,
    list_style_profiles,
    load_dataset_dataframe,
    load_unified_analyses,
    save_plot_recipe,
    save_style_profile,
)
from petrolab.dataframe_utils import (
    apply_column_filters,
    apply_quick_filter,
    dataset_label,
    row_identity,
)
from petrolab.io_utils import numeric_candidates
from petrolab.minerals.formulae import calculate_formula, methods_for
from petrolab.minerals.registry import MINERALS
from petrolab.plot_presets import JOURNAL_PRESETS
from petrolab.plotting import MARKERS, build_scatter, figure_png_bytes, figure_svg_bytes
from petrolab.services.image_service import list_all_images
from petrolab.ui.components import collect_related_images, render_asset_gallery, render_project_selector
from petrolab.ui.pages import render_analyses_page, render_home_page, render_images_page, render_projects_page, render_sources_page

st.set_page_config(page_title="ПетроЛаб", page_icon="◈", layout="wide")
ensure_storage()

st.markdown(
    """
    <style>
    .block-container {padding-top: 1.2rem; padding-bottom: 3rem; max-width: 1650px;}
    h1, h2, h3 {letter-spacing: -0.02em;}
    [data-testid="stMetric"] {border: 1px solid rgba(80,80,80,.14); padding: 12px; border-radius: 12px;}
    .small-note {font-size: .88rem; opacity: .75;}
    </style>
    """,
    unsafe_allow_html=True,
)

for key, default in {
    "working_df": None,
    "working_meta": {},
    "loaded_recipe": None,
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

def style_df_from_groups(groups: list[str], existing: dict | None = None) -> pd.DataFrame:
    existing = existing or {}
    rows = []
    for i, name in enumerate(groups):
        raw = existing.get(str(name), {})
        rows.append({"Группа": str(name), "Маркер": raw.get("marker", MARKERS[i % len(MARKERS)]), "Размер ×": float(raw.get("size_multiplier", 1.0) or 1.0), "Alpha": float(raw.get("alpha", 0.9) or 0.9), "Заливка": bool(raw.get("filled", True))})
    return pd.DataFrame(rows)


def style_map_from_df(df: pd.DataFrame) -> dict:
    styles = {}
    for _, row in df.iterrows():
        styles[str(row["Группа"])] = {"marker": row["Маркер"], "size_multiplier": float(row["Размер ×"]), "alpha": float(row["Alpha"]), "filled": bool(row["Заливка"])}
    return styles

with st.sidebar:
    st.title("◈ ПетроЛаб")
    st.caption(f"Русская версия · v{__version__}")
    page = st.radio("Раздел", ["Главная", "Проекты", "Источники и импорт", "Единая база", "Изображения", "Пересчёт формул", "Минералы", "Диаграммы", "Экспорт", "Журнал изменений"], label_visibility="collapsed")
    st.divider()
    st.caption("Локальная база SQLite. Анализы связываются с исходными Excel, а изображения — с набором, полем или отдельной точкой.")

if page == "Главная":
    render_home_page()

elif page == "Проекты":
    render_projects_page()

elif page == "Источники и импорт":
    render_sources_page()

elif page == "Единая база":
    render_analyses_page()

elif page == "Изображения":
    render_images_page()

elif page == "Пересчёт формул":
    st.title("Пересчёт структурных формул")
    project = render_project_selector("formula_project")
    if project is None:
        st.stop()
    datasets = list_datasets(project["id"])
    if not datasets:
        st.stop()
    mapping = {dataset_label(d): d for d in datasets}
    chosen = mapping[st.selectbox("Набор данных", list(mapping), key="formula_dataset")]
    methods = methods_for(chosen["mineral_key"])
    if not methods:
        st.warning("Для этого модуля пока нет валидированного минералоспецифического пересчёта.")
        st.stop()
    method_map = {m.id: m for m in methods}
    method = method_map[st.selectbox("Метод пересчёта", list(method_map), format_func=lambda mid: method_map[mid].title_ru)]
    raw_df = load_dataset_dataframe(int(chosen["id"]), include_meta=False)
    result = calculate_formula(raw_df, chosen["mineral_key"], method.id)
    st.dataframe(result.data.head(150), width="stretch", hide_index=True, height=560)

elif page == "Минералы":
    st.title("Минералогические модули")
    for key, module in MINERALS.items():
        if key != "generic":
            with st.expander(f"{module.name_ru} · {module.group_ru}"):
                st.write(module.description)

elif page == "Диаграммы":
    st.title("Диаграммы по всей базе")
    st.write("Здесь можно брать точки из разных Excel, сохранять рецепты рисунков, применять журнальные шаблоны и быстро фильтровать базу по колонкам.")
    scope = st.radio("Область данных", ["Один проект", "Все проекты"], horizontal=True, key="plot_scope")
    project_id = None
    if scope == "Один проект":
        current_project = render_project_selector("plot_project")
        if current_project is None:
            st.stop()
        project_id = current_project["id"]
    datasets = list_datasets(project_id)
    if not datasets:
        st.stop()
    recipe_records = list_plot_recipes(project_id)
    style_records = list_style_profiles(project_id)
    with st.expander("Сохранённые рецепты графиков", expanded=False):
        if recipe_records:
            recipe_map = {f"{r['name']} · {('общий' if r['project_id'] is None else 'проект')}": r for r in recipe_records}
            chosen_recipe_label = st.selectbox("Загрузить рецепт", ["—"] + list(recipe_map), key="recipe_select")
            c_load, c_del = st.columns(2)
            if chosen_recipe_label != "—":
                chosen_recipe = recipe_map[chosen_recipe_label]
                if c_load.button("Применить рецепт", key="load_recipe_btn"):
                    st.session_state.loaded_recipe = chosen_recipe["config"]
                    st.rerun()
                if c_del.button("Удалить рецепт", key="delete_recipe_btn"):
                    delete_plot_recipe(int(chosen_recipe["id"]))
                    st.success("Рецепт удалён.")
                    st.rerun()
    recipe = st.session_state.get("loaded_recipe") or {}
    ds_labels = {dataset_label(d): int(d["id"]) for d in datasets}
    default_labels = [label for label, did in ds_labels.items() if did in recipe.get("dataset_ids", list(ds_labels.values()))] if recipe else list(ds_labels)
    selected_labels = st.multiselect("Наборы для графика", list(ds_labels), default=default_labels, key="plot_datasets")
    selected_ids = [ds_labels[x] for x in selected_labels]
    if not selected_ids:
        st.stop()
    df = load_unified_analyses(project_id, selected_ids)
    if df.empty:
        st.stop()
    minerals = sorted(df["Минерал"].dropna().astype(str).unique())
    default_minerals = recipe.get("minerals", minerals) if recipe else minerals
    selected_minerals = st.multiselect("Минералы", minerals, default=[m for m in default_minerals if m in minerals], format_func=lambda k: MINERALS.get(k, MINERALS["generic"]).name_ru, key="plot_minerals")
    if selected_minerals:
        df = df[df["Минерал"].astype(str).isin(selected_minerals)]
    query = st.text_input("Быстрый строковый поиск", value=recipe.get("query", ""), key="plot_search")
    df = apply_quick_filter(df, query)
    with st.expander("Фильтры по колонкам", expanded=False):
        candidate_filter_columns = [c for c in df.columns if not str(c).startswith("_") and df[c].nunique(dropna=True) <= 100]
        preferred_filter_columns = [c for c in ["Проект", "Набор", "Минерал", "Источник", "Лист", "Group", "Type", "Generation", "Sample", "Grain"] if c in candidate_filter_columns]
        filter_choices = st.multiselect("Колонки для фильтрации", preferred_filter_columns + [c for c in candidate_filter_columns if c not in preferred_filter_columns], default=[c for c in recipe.get("column_filters", {}).keys() if c in candidate_filter_columns], key="column_filter_columns")
        chosen_filters = {}
        for col in filter_choices:
            values = sorted(df[col].dropna().astype(str).unique().tolist())
            defaults = [v for v in recipe.get("column_filters", {}).get(col, []) if v in values]
            chosen_filters[col] = st.multiselect(f"{col}", values, default=defaults, key=f"filter_vals_{col}")
        if chosen_filters:
            df = apply_column_filters(df, chosen_filters)
    numeric = numeric_candidates(df)
    if len(numeric) < 2:
        st.error("Недостаточно числовых колонок после применения фильтров.")
        st.stop()
    preset_names = list(JOURNAL_PRESETS)
    preset_default = recipe.get("journal_preset", "Свой") if recipe.get("journal_preset", "Свой") in JOURNAL_PRESETS else "Свой"
    preset = st.selectbox("Шаблон графика", preset_names, index=preset_names.index(preset_default), key="journal_preset")
    preset_cfg = JOURNAL_PRESETS[preset]
    categorical = [c for c in df.columns if not str(c).startswith("_") and c not in numeric and df[c].nunique(dropna=True) <= 80]
    preferred_groups = [c for c in ["Набор", "Минерал", "Источник", "Лист"] if c in df.columns]
    categorical = preferred_groups + [c for c in categorical if c not in preferred_groups]
    c1, c2, c3 = st.columns(3)
    x = c1.selectbox("Ось X", numeric, index=(numeric.index(recipe.get("x")) if recipe.get("x") in numeric else 0))
    y = c2.selectbox("Ось Y", numeric, index=(numeric.index(recipe.get("y")) if recipe.get("y") in numeric else min(1, len(numeric) - 1)))
    group_options = ["Без группировки"] + categorical
    group_default = recipe.get("group_col") if recipe.get("group_col") in categorical else "Без группировки"
    group = c3.selectbox("Группировка", group_options, index=group_options.index(group_default))
    group_col = None if group == "Без группировки" else group
    c4, c5, c6, c7 = st.columns(4)
    x_label = c4.text_input("Подпись X", value=recipe.get("x_label", x))
    y_label = c5.text_input("Подпись Y", value=recipe.get("y_label", y))
    marker_size = c6.slider("Размер маркеров", 10, 180, int(recipe.get("marker_size", preset_cfg["marker_size"])), 2)
    title = c7.text_input("Заголовок", value=recipe.get("title", ""))
    with st.expander("Оси, подписи и журнальное оформление", expanded=False):
        a1, a2, a3, a4 = st.columns(4)
        x_min = a1.number_input("X min", value=recipe.get("x_min", None), step=0.1)
        x_max = a2.number_input("X max", value=recipe.get("x_max", None), step=0.1)
        y_min = a3.number_input("Y min", value=recipe.get("y_min", None), step=0.1)
        y_max = a4.number_input("Y max", value=recipe.get("y_max", None), step=0.1)
        b1, b2, b3, b4 = st.columns(4)
        log_x = b1.checkbox("Логарифмическая X", value=recipe.get("log_x", False))
        log_y = b2.checkbox("Логарифмическая Y", value=recipe.get("log_y", False))
        show_grid = b3.checkbox("Сетка", value=recipe.get("show_grid", preset_cfg["show_grid"]))
        monochrome = b4.checkbox("Ч/б режим", value=recipe.get("monochrome", preset_cfg["monochrome"]))
        d1, d2, d3 = st.columns(3)
        show_legend = d1.checkbox("Показывать легенду", value=recipe.get("show_legend", preset_cfg["show_legend"]))
        annotate = d2.checkbox("Подписывать точки", value=recipe.get("annotate", False))
        label_candidates = [c for c in df.columns if not str(c).startswith("_") and df[c].nunique(dropna=True) <= max(200, len(df))]
        label_col_choice = d3.selectbox("Поле для подписи", ["—"] + label_candidates, index=(1 + label_candidates.index(recipe.get("label_col")) if recipe.get("label_col") in label_candidates else 0))
        label_col = None if label_col_choice == "—" else label_col_choice
        annotate_top_n = st.slider("Сколько точек подписывать", 1, 1000, int(recipe.get("annotate_top_n", 25))) if annotate and label_col else 0
        e1, e2, e3, e4 = st.columns(4)
        figure_width = e1.number_input("Ширина фигуры", min_value=3.0, max_value=20.0, value=float(recipe.get("figure_width", preset_cfg["figure_width"])), step=0.1)
        figure_height = e2.number_input("Высота фигуры", min_value=3.0, max_value=20.0, value=float(recipe.get("figure_height", preset_cfg["figure_height"])), step=0.1)
        font_size = e3.number_input("Размер шрифта", min_value=6.0, max_value=24.0, value=float(recipe.get("font_size", preset_cfg["font_size"])), step=0.5)
        tick_size = e4.number_input("Размер подписей делений", min_value=6.0, max_value=24.0, value=float(recipe.get("tick_size", preset_cfg["tick_size"])), step=0.5)
        f1, f2 = st.columns(2)
        spine_width = f1.number_input("Толщина осей", min_value=0.5, max_value=3.0, value=float(recipe.get("spine_width", preset_cfg["spine_width"])), step=0.1)
        title_size = f2.number_input("Размер заголовка", min_value=6.0, max_value=28.0, value=float(recipe.get("title_size", float(recipe.get("font_size", preset_cfg["font_size"])) + 1.0)), step=0.5)
    style_map = {}
    if group_col and group_col in df.columns:
        group_values = sorted([str(v) for v in df[group_col].dropna().astype(str).unique().tolist()])
        with st.expander("Профили маркеров по группам", expanded=False):
            profile_map = {f"{r['name']} · {r['grouping_column'] or 'без поля'}": r for r in style_records if not r['grouping_column'] or r['grouping_column'] == group_col}
            selected_profile = st.selectbox("Готовый профиль", ["—"] + list(profile_map), key="style_profile_select") if profile_map else "—"
            existing_style = profile_map[selected_profile]["styles"] if profile_map and selected_profile != "—" else recipe.get("style_map", {})
            style_editor = st.data_editor(style_df_from_groups(group_values, existing=existing_style), width="stretch", hide_index=True, column_config={"Маркер": st.column_config.SelectboxColumn("Маркер", options=MARKERS), "Размер ×": st.column_config.NumberColumn("Размер ×", min_value=0.2, max_value=5.0, step=0.1), "Alpha": st.column_config.NumberColumn("Alpha", min_value=0.1, max_value=1.0, step=0.05), "Заливка": st.column_config.CheckboxColumn("Заливка")}, key="style_editor")
            style_map = style_map_from_df(style_editor)
            s1, s2 = st.columns(2)
            profile_name = s1.text_input("Название профиля стилей", value=recipe.get("style_profile_name", ""), key="style_profile_name")
            save_scope_project = s2.checkbox("Сохранить как проектный профиль", value=True if project_id is not None else False, disabled=project_id is None)
            if st.button("Сохранить профиль стилей", key="save_style_profile"):
                save_style_profile(profile_name or f"Профиль {group_col}", group_col, style_map, project_id=project_id if save_scope_project else None)
                st.success("Профиль стилей сохранён.")
                st.rerun()
    needed = [x, y] + ([group_col] if group_col else []) + ([label_col] if label_col else [])
    base_cols = [c for c in ["_analysis_id", "_dataset_id", "_source_row", "Проект", "Набор", "Минерал", "Источник", "Лист"] if c in df.columns]
    plot_df = df[[c for c in base_cols + needed if c in df.columns]].copy()
    plot_df[x] = pd.to_numeric(plot_df[x], errors="coerce")
    plot_df[y] = pd.to_numeric(plot_df[y], errors="coerce")
    plot_df = plot_df.dropna(subset=[x, y])
    fig = build_scatter(plot_df, x, y, group_col, x_label=x_label, y_label=y_label, title=title, marker_size=marker_size, xlim=(x_min, x_max), ylim=(y_min, y_max), log_x=log_x, log_y=log_y, show_grid=show_grid, style_map=style_map, monochrome=monochrome, show_legend=show_legend, annotate=annotate, label_col=label_col, annotate_top_n=annotate_top_n, figure_size=(figure_width, figure_height), font_size=font_size, tick_size=tick_size, title_size=title_size, spine_width=spine_width)
    st.pyplot(fig, width="content")
    png = figure_png_bytes(fig, dpi=600)
    svg = figure_svg_bytes(fig)
    plt.close(fig)
    b1, b2, b3 = st.columns(3)
    b1.download_button("PNG · 600 dpi", png, file_name="petrolab_plot.png", mime="image/png", width="stretch")
    b2.download_button("SVG", svg, file_name="petrolab_plot.svg", mime="image/svg+xml", width="stretch")
    plot_excel = io.BytesIO()
    with pd.ExcelWriter(plot_excel, engine="openpyxl") as writer:
        plot_df.to_excel(writer, index=False, sheet_name="Точки графика")
        pd.DataFrame([{"journal_preset": preset, "x": x, "y": y, "group_col": group_col or "", "x_label": x_label, "y_label": y_label, "title": title, "marker_size": marker_size, "x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max, "log_x": log_x, "log_y": log_y, "show_grid": show_grid, "monochrome": monochrome, "show_legend": show_legend, "annotate": annotate, "label_col": label_col or "", "annotate_top_n": annotate_top_n, "figure_width": figure_width, "figure_height": figure_height, "font_size": font_size, "tick_size": tick_size, "spine_width": spine_width, "title_size": title_size, "query": query, "column_filters": json.dumps(chosen_filters, ensure_ascii=False)}]).to_excel(writer, index=False, sheet_name="Настройки")
    b3.download_button("Данные графика · Excel", plot_excel.getvalue(), file_name="petrolab_plot_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    with st.expander("Сохранить текущий рецепт графика", expanded=False):
        recipe_name = st.text_input("Название рецепта", value=recipe.get("name", ""), key="save_recipe_name")
        recipe_project = st.checkbox("Сохранить как проектный рецепт", value=True if project_id is not None else False, disabled=project_id is None)
        current_recipe = {"dataset_ids": selected_ids, "minerals": selected_minerals, "query": query, "column_filters": chosen_filters, "journal_preset": preset, "x": x, "y": y, "group_col": group_col, "x_label": x_label, "y_label": y_label, "title": title, "marker_size": marker_size, "x_min": x_min, "x_max": x_max, "y_min": y_min, "y_max": y_max, "log_x": log_x, "log_y": log_y, "show_grid": show_grid, "monochrome": monochrome, "show_legend": show_legend, "annotate": annotate, "label_col": label_col, "annotate_top_n": annotate_top_n, "figure_width": figure_width, "figure_height": figure_height, "font_size": font_size, "tick_size": tick_size, "spine_width": spine_width, "title_size": title_size, "style_map": style_map}
        if st.button("Сохранить рецепт", key="save_recipe_button"):
            save_plot_recipe(recipe_name or f"{x} vs {y}", current_recipe, project_id=project_id if recipe_project else None)
            st.success("Рецепт сохранён.")
            st.rerun()
    st.subheader("Точки, вошедшие в график")
    st.dataframe(plot_df, width="stretch", hide_index=True, height=350)
    if not plot_df.empty:
        point_map = {f"{row_identity(row)} · {row.get('Источник', '')} · строка {row.get('_source_row', '—')}": str(row["_analysis_id"]) for _, row in plot_df.head(3000).iterrows()}
        chosen_point = st.selectbox("Открыть точку с графика", list(point_map), key="plot_point_select")
        selected_row = plot_df[plot_df["_analysis_id"].astype(str) == point_map[chosen_point]].iloc[0]
        render_asset_gallery(collect_related_images(selected_row, project_id=project_id), max_items=10, width=650)

elif page == "Экспорт":
    st.title("Экспорт общей базы")
    datasets = list_datasets()
    if not datasets:
        st.stop()
    ds_labels = {dataset_label(d): int(d["id"]) for d in datasets}
    selected = st.multiselect("Наборы", list(ds_labels), default=list(ds_labels))
    ids = [ds_labels[x] for x in selected]
    if not ids:
        st.stop()
    df = load_unified_analyses(dataset_ids=ids)
    st.dataframe(df.head(80), width="stretch", hide_index=True)
    export_df = df[[c for c in df.columns if not str(c).startswith("_")]].copy()
    excel_buf = io.BytesIO()
    with pd.ExcelWriter(excel_buf, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Все анализы")
        pd.DataFrame(list_all_images()).to_excel(writer, index=False, sheet_name="Изображения")
        recipes = list_plot_recipes()
        if recipes:
            pd.DataFrame([{"id": r["id"], "project_id": r["project_id"], "name": r["name"], "created_at": r["created_at"], "updated_at": r["updated_at"], "config": json.dumps(r["config"], ensure_ascii=False)} for r in recipes]).to_excel(writer, index=False, sheet_name="Рецепты графиков")
        profiles = list_style_profiles()
        if profiles:
            pd.DataFrame([{"id": r["id"], "project_id": r["project_id"], "name": r["name"], "grouping_column": r["grouping_column"], "created_at": r["created_at"], "updated_at": r["updated_at"], "styles": json.dumps(r["styles"], ensure_ascii=False)} for r in profiles]).to_excel(writer, index=False, sheet_name="Профили стилей")
    st.download_button("Единый Excel", excel_buf.getvalue(), file_name="PetroLab_единая_база.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", type="primary")

elif page == "Журнал изменений":
    st.title("Журнал изменений")
    rows = list_change_log(limit=2000)
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=700)
    else:
        st.caption("Изменений пока нет.")
