from __future__ import annotations

import hashlib
import io

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.grain_profiles import (
    ORDER_MODES,
    build_grain_profile_figure,
    figure_bytes,
    grain_profile_recipe,
    prepare_grain_profile,
    recipe_json_bytes,
)
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.project_context import active_project


def _numeric_candidates(dataframe: pd.DataFrame) -> list[str]:
    candidates: list[str] = []
    for column in dataframe.columns:
        if str(column).startswith("_"):
            continue
        numeric = pd.to_numeric(dataframe[column], errors="coerce")
        if int(numeric.notna().sum()) >= 2:
            candidates.append(str(column))
    return candidates


def _identity_columns(dataframe: pd.DataFrame) -> list[str]:
    preferred = [
        "Sample", "Образец", "Point", "Точка", "Generation", "Поколение",
        "Mineral", "Минерал", "Набор", "Источник", "Лист",
    ]
    return [column for column in preferred if column in dataframe.columns]


def _point_label(row: pd.Series) -> str:
    values = []
    for column in ["Sample", "Образец", "Point", "Точка", "Generation", "Поколение"]:
        if column in row.index:
            value = str(row.get(column) or "").strip()
            if value and value.lower() != "nan":
                values.append(value)
    analysis_id = str(row.get("_analysis_id") or "")
    suffix = analysis_id[:8] if analysis_id else ""
    return " · ".join(dict.fromkeys(values)) + (f" · {suffix}" if suffix else "")


def _quick_filter(dataframe: pd.DataFrame, query: str) -> pd.DataFrame:
    text = str(query or "").strip().casefold()
    if not text:
        return dataframe
    columns = _identity_columns(dataframe)
    if not columns:
        return dataframe
    mask = pd.Series(False, index=dataframe.index, dtype=bool)
    for column in columns:
        mask |= dataframe[column].astype(str).str.casefold().str.contains(text, regex=False, na=False)
    return dataframe.loc[mask].copy()


def _exact_order(dataframe: pd.DataFrame, analysis_ids: list[str]) -> tuple[pd.DataFrame, list[str]]:
    ids = dataframe["_analysis_id"].astype(str)
    duplicate_ids = ids[ids.duplicated(keep=False)]
    if not duplicate_ids.empty:
        raise ValueError("В выбранной таблице один analysis_id встречается несколько раз")
    by_id = {str(row["_analysis_id"]): row for _, row in dataframe.iterrows()}
    missing = [analysis_id for analysis_id in analysis_ids if analysis_id not in by_id]
    ordered = [by_id[analysis_id] for analysis_id in analysis_ids if analysis_id in by_id]
    return pd.DataFrame(ordered).reset_index(drop=True), missing


def _xlsx_bytes(dataframe: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    visible = [column for column in dataframe.columns if not str(column).startswith("_")]
    export = dataframe[["_profile_order", "_profile_x", *visible]].copy()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export.to_excel(writer, index=False, sheet_name="Grain profile")
    return buffer.getvalue()


def render_grain_profile_page() -> None:
    project = active_project()
    render_page_header(
        "Профиль по зерну",
        "Постройте последовательность от core к rim по 5–100+ аналитическим точкам. Порядок и расстояние задаются явно; PetroLab не соединяет точки разных изображений по догадке.",
        eyebrow="Исследование",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        return

    project_id = int(project["id"])
    datasets = list_accessible_datasets(project_id)
    if not datasets:
        st.info("В проекте пока нет аналитических наборов.")
        return
    by_id = {int(item["id"]): item for item in datasets}

    route_context = st.session_state.get("grain_profile_context")
    route_context = route_context if isinstance(route_context, dict) else {}
    try:
        route_project_id = int(route_context.get("project_id"))
    except (TypeError, ValueError):
        route_project_id = None
    route_active = route_project_id == project_id
    raw_routed_dataset_ids = list(st.session_state.get("grain_profile_dataset_ids", [])) if route_active else []
    routed_dataset_ids = [int(value) for value in raw_routed_dataset_ids if int(value) in by_id]
    missing_routed_datasets = [int(value) for value in raw_routed_dataset_ids if int(value) not in by_id]
    if missing_routed_datasets:
        st.error("Точный отбор ссылается на dataset, недоступный в текущем проекте: " + ", ".join(map(str, missing_routed_datasets[:8])))
        return

    selected_dataset_ids = st.multiselect(
        "Наборы данных",
        list(by_id),
        default=routed_dataset_ids,
        format_func=lambda value: dataset_label(by_id[int(value)]),
        key=f"grain_profile_datasets_{project_id}",
        placeholder="Выберите набор с точками профиля",
    )
    if not selected_dataset_ids:
        return

    dataframe = load_unified_with_derived(project_id, [int(value) for value in selected_dataset_ids])
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        st.warning("В выбранных наборах нет аналитических точек.")
        return

    q1, q2 = st.columns([2, 1])
    query = q1.text_input(
        "Быстро сузить точки",
        key=f"grain_profile_search_{project_id}",
        placeholder="Например: KIV-2 phlogopite core",
    )
    filtered = _quick_filter(dataframe, query)
    routed_ids = [str(value) for value in st.session_state.get("grain_profile_analysis_ids", []) if str(value)] if route_active else []
    if routed_ids:
        try:
            filtered, missing_ids = _exact_order(filtered, routed_ids)
        except ValueError as exc:
            st.error(str(exc))
            return
        if missing_ids and not str(query or "").strip():
            st.error("Точный отбор потерял analysis_id: " + ", ".join(missing_ids[:8]))
            return
        if missing_ids:
            q2.caption(f"Быстрый фильтр исключил {len(missing_ids)} точек из точного отбора")
        q2.metric("Точный отбор", len(filtered))
        if q2.button("Снять точный отбор", key=f"grain_profile_clear_exact_{project_id}"):
            for key in ("grain_profile_dataset_ids", "grain_profile_analysis_ids", "grain_profile_context"):
                st.session_state.pop(key, None)
            st.rerun()
    else:
        q2.metric("Найдено точек", len(filtered))
    if filtered.empty:
        st.warning("После фильтра не осталось точек.")
        return

    render_section_header("Точки профиля", "Выберите физически относящиеся к одному traverse точки")
    label_map = {str(row["_analysis_id"]): _point_label(row) for _, row in filtered.iterrows()}
    options = list(label_map)
    selection_token = hashlib.sha1(
        (f"{project_id}|" + ",".join(map(str, selected_dataset_ids)) + "|" + ",".join(routed_ids)).encode("utf-8")
    ).hexdigest()[:12]
    selection_key = f"grain_profile_selected_ids_{selection_token}"
    default_ids = options if routed_ids or len(options) <= 120 else []
    if not routed_ids and len(options) > 120:
        st.caption(f"Найдено {len(options)} точек. PetroLab больше не выбирает первые 120 молча — выберите нужный traverse явно.")
        if st.button(f"Выбрать все {len(options)} точек", key=f"grain_profile_select_all_{selection_token}"):
            st.session_state[selection_key] = options
            st.rerun()
    selected_ids = st.multiselect(
        "Точки",
        options,
        default=default_ids,
        format_func=lambda value: label_map[str(value)],
        key=selection_key,
    )
    if len(selected_ids) < 2:
        st.info("Для профиля выберите хотя бы две точки.")
        return
    render_badges([(f"точек · {len(selected_ids)}", "accent")])

    render_section_header("Порядок и расстояние", "Порядок должен быть физически определён")
    mode_by_title = {title: key for key, title in ORDER_MODES.items()}
    default_title = "Номер из подписи точки" if any(column in filtered.columns for column in ["Point", "Точка"]) else "Порядок выбранных analysis_id / строк"
    mode_title = st.selectbox(
        "Как задать порядок",
        list(mode_by_title),
        index=list(mode_by_title).index(default_title) if default_title in mode_by_title else 0,
        key=f"grain_profile_order_mode_{project_id}",
    )
    order_mode = mode_by_title[mode_title]
    columns = [str(column) for column in filtered.columns if not str(column).startswith("_")]
    numeric_columns = _numeric_candidates(filtered)
    order_column = ""
    label_column = ""
    distance_column = ""
    x_column = ""
    y_column = ""
    frame_column = ""

    if order_mode == "explicit":
        if not numeric_columns:
            st.error("Нет числовой колонки для порядка точек.")
            return
        order_column = st.selectbox("Колонка порядка", numeric_columns, key=f"grain_profile_order_column_{project_id}")
    elif order_mode == "label_number":
        suggested = "Point" if "Point" in columns else ("Точка" if "Точка" in columns else columns[0])
        label_column = st.selectbox(
            "Колонка с подписями точек",
            columns,
            index=columns.index(suggested),
            key=f"grain_profile_label_column_{project_id}",
        )
    elif order_mode == "distance":
        if not numeric_columns:
            st.error("Нет числовой колонки расстояния.")
            return
        distance_column = st.selectbox("Колонка расстояния", numeric_columns, key=f"grain_profile_distance_column_{project_id}")
    elif order_mode == "geometry":
        if not numeric_columns:
            st.error("Нет числовых координат для геометрического профиля.")
            return
        g1, g2, g3, g4 = st.columns(4)
        order_column = g1.selectbox("Порядок", numeric_columns, key=f"grain_profile_geometry_order_{project_id}")
        x_column = g2.selectbox("X", numeric_columns, key=f"grain_profile_geometry_x_{project_id}")
        y_column = g3.selectbox("Y", numeric_columns, key=f"grain_profile_geometry_y_{project_id}")
        frame_column = g4.selectbox("Система координат / image id", columns, key=f"grain_profile_geometry_frame_{project_id}")
        st.caption("Geometry разрешён только в одной системе координат и при уже известном порядке traverse. Расстояние наследует единицы X/Y; это µm только для калиброванных координат в µm.")

    b1, b2 = st.columns(2)
    normalize = b1.checkbox("Нормировать расстояние 0–1", value=False, key=f"grain_profile_normalize_{project_id}")
    reverse = b2.checkbox("Развернуть направление профиля", value=False, key=f"grain_profile_reverse_{project_id}")

    try:
        result = prepare_grain_profile(
            filtered,
            analysis_ids=selected_ids,
            order_mode=order_mode,
            order_column=order_column,
            label_column=label_column,
            distance_column=distance_column,
            x_column=x_column,
            y_column=y_column,
            coordinate_frame_column=frame_column,
            normalize_distance=bool(normalize),
            reverse=bool(reverse),
        )
    except Exception as exc:
        st.error(f"Профиль не построен: {exc}")
        return

    render_section_header("Что показать", "Пропуски и бесконечные derived-значения остаются разрывами, а не нулями")
    numeric = _numeric_candidates(result.dataframe)
    default_y = [column for column in ["MgO", "FeO", "TiO2", "Cr2O3"] if column in numeric][:2]
    y_columns = st.multiselect(
        "Величины Y",
        numeric,
        default=default_y,
        key=f"grain_profile_y_columns_{project_id}",
    )
    if not y_columns:
        return

    with st.expander("Зоны core / mantle / rim", expanded=False):
        zones = st.data_editor(
            pd.DataFrame(columns=["label", "start", "end"]),
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "label": st.column_config.TextColumn("Зона"),
                "start": st.column_config.NumberColumn("От"),
                "end": st.column_config.NumberColumn("До"),
            },
            key=f"grain_profile_zones_{project_id}",
        ).to_dict("records")

    try:
        figure = build_grain_profile_figure(result, y_columns, zones=zones)
    except Exception as exc:
        st.error(f"Не удалось нарисовать профиль: {exc}")
        return
    st.pyplot(figure, width="stretch")

    ordered = result.dataframe
    preview_columns = ["_profile_order", "_profile_x"] + [
        column for column in ["Sample", "Образец", "Point", "Точка", *y_columns]
        if column in ordered.columns
    ]
    st.dataframe(ordered[preview_columns], width="stretch", hide_index=True)

    render_section_header("Экспорт", "Рисунок, точки в точном порядке и воспроизводимый рецепт")
    recipe = grain_profile_recipe(result, y_columns=y_columns, zones=zones)
    e1, e2, e3, e4 = st.columns(4)
    e1.download_button("SVG", figure_bytes(figure, "svg", 600), file_name="petrolab_grain_profile.svg", mime="image/svg+xml", width="stretch")
    e2.download_button("PNG 600 dpi", figure_bytes(figure, "png", 600), file_name="petrolab_grain_profile.png", mime="image/png", width="stretch")
    e3.download_button("XLSX точек", _xlsx_bytes(ordered), file_name="petrolab_grain_profile.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
    e4.download_button("Recipe JSON", recipe_json_bytes(recipe), file_name="petrolab_grain_profile.recipe.json", mime="application/json", width="stretch")
    plt.close(figure)
