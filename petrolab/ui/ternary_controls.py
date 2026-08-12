from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from petrolab.io_utils import numeric_candidates
from petrolab.ternary_overlays import TernaryOverlay, get_ternary_overlay
from petrolab.ternary_presets import (
    TernaryPreset,
    apply_preset_projection,
    available_ternary_presets,
)


@dataclass(frozen=True)
class TernarySelection:
    dataframe: pd.DataFrame
    mode: str
    preset_id: str
    a_col: str
    b_col: str
    c_col: str
    a_label: str
    b_label: str
    c_label: str
    overlay: TernaryOverlay | None
    show_overlay: bool


def _custom_selection(dataframe: pd.DataFrame, recipe: dict) -> TernarySelection:
    numeric = numeric_candidates(dataframe)
    if len(numeric) < 3:
        raise ValueError("Для треугольной диаграммы нужны минимум три числовые колонки")

    saved = recipe.get("ternary_components", {}) if isinstance(recipe.get("ternary_components", {}), dict) else {}
    c1, c2, c3 = st.columns(3)
    a_default = saved.get("a") if saved.get("a") in numeric else numeric[0]
    b_default = saved.get("b") if saved.get("b") in numeric and saved.get("b") != a_default else numeric[1]
    c_default = (
        saved.get("c")
        if saved.get("c") in numeric and saved.get("c") not in {a_default, b_default}
        else numeric[2]
    )
    a_col = c1.selectbox("Компонент A · левая вершина", numeric, index=numeric.index(a_default), key="ternary_a")
    b_col = c2.selectbox("Компонент B · правая вершина", numeric, index=numeric.index(b_default), key="ternary_b")
    c_col = c3.selectbox("Компонент C · верхняя вершина", numeric, index=numeric.index(c_default), key="ternary_c")
    l1, l2, l3 = st.columns(3)
    a_label = l1.text_input("Подпись A", value=str(saved.get("a_label", a_col)), key="ternary_a_label")
    b_label = l2.text_input("Подпись B", value=str(saved.get("b_label", b_col)), key="ternary_b_label")
    c_label = l3.text_input("Подпись C", value=str(saved.get("c_label", c_col)), key="ternary_c_label")
    return TernarySelection(
        dataframe=dataframe,
        mode="Своя диаграмма",
        preset_id="",
        a_col=a_col,
        b_col=b_col,
        c_col=c_col,
        a_label=a_label,
        b_label=b_label,
        c_label=c_label,
        overlay=None,
        show_overlay=False,
    )


def _preset_selection(dataframe: pd.DataFrame, recipe: dict) -> TernarySelection | None:
    available = available_ternary_presets(dataframe.columns)
    if not available:
        return None

    labels = {preset.title_ru: preset for preset in available}
    saved_id = recipe.get("ternary_preset_id")
    default_label = next(
        (label for label, preset in labels.items() if preset.preset_id == saved_id),
        next(iter(labels)),
    )
    chosen = st.selectbox(
        "Минералогический шаблон",
        list(labels),
        index=list(labels).index(default_label),
        key="ternary_preset",
    )
    preset: TernaryPreset = labels[chosen]
    st.caption(preset.description_ru)

    projected, components = apply_preset_projection(dataframe, preset)
    overlay = get_ternary_overlay(preset.field_overlay_id)
    show_overlay = False
    if overlay is not None:
        show_overlay = st.checkbox(
            "Показывать классификационные поля",
            value=bool(recipe.get("show_classification_overlay", True)),
            key="ternary_show_overlay",
        )
        with st.expander("Источник классификационной схемы", expanded=False):
            st.write(overlay.source_citation)
            st.caption(f"DOI: {overlay.source_doi}")
            if overlay.note_ru:
                st.info(overlay.note_ru)

    return TernarySelection(
        dataframe=projected,
        mode="Шаблон",
        preset_id=preset.preset_id,
        a_col=components[0],
        b_col=components[1],
        c_col=components[2],
        a_label=preset.a_label,
        b_label=preset.b_label,
        c_label=preset.c_label,
        overlay=overlay,
        show_overlay=show_overlay,
    )


def render_ternary_selection(dataframe: pd.DataFrame, recipe: dict) -> TernarySelection:
    """Render preset/custom controls and return a projected, source-aware ternary view."""
    numeric = numeric_candidates(dataframe)
    if len(numeric) < 3:
        raise ValueError("Для треугольной диаграммы нужны минимум три числовые колонки")

    mode_default = recipe.get("ternary_mode", "Шаблон")
    mode = st.radio(
        "Режим ternary",
        ["Шаблон", "Своя диаграмма"],
        horizontal=True,
        index=0 if mode_default == "Шаблон" else 1,
        key="ternary_mode",
    )
    if mode == "Шаблон":
        selection = _preset_selection(dataframe, recipe)
        if selection is not None:
            return selection
        st.warning(
            "В текущих данных нет полного набора компонентов готового шаблона. "
            "Сначала сохраните соответствующий пересчёт формулы либо выберите свои три компонента."
        )
    return _custom_selection(dataframe, recipe)
