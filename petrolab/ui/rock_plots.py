from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab.db import dataset_is_accessible
from petrolab.derived import load_unified_with_derived
from petrolab.extended_plotting import (
    NORMALIZATION_REFERENCES,
    REE_ORDER,
    SPIDER_ORDER,
    available_elements,
    build_pattern_figure,
    prepare_pattern,
)
from petrolab.repositories.rock_repository import composition_wide, isotope_wide, list_mineral_links
from petrolab.rock_plotting import build_rhodes_figure, build_rock_scatter, build_tas_figure, figure_bytes
from petrolab.services.rock_service import composition_dict, inferred_whole_rock_fe3_fraction, measured_olivine_kd, whole_rock_mg_number
from petrolab.ui.plot_style_controls import render_figure_style_controls
from petrolab.visualization_presets import POINT_STYLE_PRESETS


def _download_figure(fig, filename_stem: str, style, key_prefix: str) -> None:
    c1, c2 = st.columns(2)
    c1.download_button(
        "PNG", figure_bytes(fig, "png", style.dpi), file_name=f"{filename_stem}.png",
        mime="image/png", key=f"{key_prefix}_png",
    )
    c2.download_button(
        "SVG", figure_bytes(fig, "svg", style.dpi), file_name=f"{filename_stem}.svg",
        mime="image/svg+xml", key=f"{key_prefix}_svg",
    )


def _rock_scatter_style_kwargs(style) -> dict:
    return {
        "font_family": style.font_family,
        "font_size": style.font_size,
        "tick_size": style.tick_size,
        "label_size": style.label_size,
        "marker_size": style.marker_size,
        "line_width": style.line_width,
        "spine_width": style.spine_width,
        "point_style_name": style.point_style_name,
        "monochrome": style.monochrome,
        "show_legend": style.show_legend,
        "grid": style.grid,
        "figure_size": (style.width_in, style.height_in),
    }


def render_rock_plots(project_id: int, selected_rock: dict) -> None:
    """Render bulk-rock and mineral–rock plots without owning rock CRUD state."""
    wide = composition_wide(project_id)
    if wide.empty:
        st.info("Сначала внесите валовый химический состав.")
        return

    tab_tas, tab_harker, tab_pattern, tab_iso, tab_rhodes = st.tabs(
        ["TAS", "Harker / бинарные", "REE / Spider", "Изотопы", "Mineral–rock / Rhodes"]
    )

    with tab_tas:
        required = {"SiO2", "Na2O", "K2O"}
        if required.issubset(wide.columns):
            style = render_figure_style_controls(wide, key_prefix="rock_tas")
            label_points = st.checkbox("Подписывать названия пород", value=True, key="rock_tas_labels")
            fig = build_tas_figure(
                wide,
                group_column="Massif" if "Massif" in wide else None,
                label_column="Rock" if label_points else None,
                **_rock_scatter_style_kwargs(style),
            )
            st.pyplot(fig, width="stretch")
            _download_figure(fig, "TAS", style, "rock_tas")
            plt.close(fig)
            st.caption(
                "TAS: Le Bas et al. (1986), IUGS. Basanite/tephrite и trachyte/trachydacite "
                "не разделяются одной позицией на TAS без дополнительных критериев."
            )
        else:
            st.info("Для TAS нужны SiO2, Na2O и K2O.")

    with tab_harker:
        numeric = [
            column for column in wide.columns
            if pd.to_numeric(wide[column], errors="coerce").notna().sum() >= 2
            and not str(column).startswith("_")
        ]
        if len(numeric) >= 2:
            x_default = "SiO2" if "SiO2" in numeric else numeric[0]
            c1, c2 = st.columns(2)
            x = c1.selectbox("X", numeric, index=numeric.index(x_default), key="rock_harker_x")
            y_choices = [column for column in numeric if column != x]
            y = c2.selectbox("Y", y_choices, key="rock_harker_y")
            l1, l2 = st.columns(2)
            x_label = l1.text_input("Подпись X", value=x, key="rock_harker_xlabel")
            y_label = l2.text_input("Подпись Y", value=y, key="rock_harker_ylabel")
            style = render_figure_style_controls(wide, key_prefix="rock_harker")
            fig = build_rock_scatter(
                wide,
                x,
                y,
                group_column="Massif" if "Massif" in wide else None,
                label_column=style.point_label_column if style.label_points else None,
                title=f"{y} vs {x}",
                x_label=x_label,
                y_label=y_label,
                **_rock_scatter_style_kwargs(style),
            )
            st.pyplot(fig, width="stretch")
            _download_figure(fig, f"{y}_vs_{x}", style, "rock_harker")
            plt.close(fig)
        else:
            st.info("Для бинарной диаграммы нужны минимум две числовые колонки в нескольких породах.")

    with tab_pattern:
        mode = st.segmented_control("Тип", ["REE", "Spider"], default="REE", key="rock_pattern_mode") or "REE"
        order = REE_ORDER if mode == "REE" else SPIDER_ORDER
        reference_names = list(NORMALIZATION_REFERENCES)
        ref_name = st.selectbox(
            "Нормировка",
            reference_names,
            index=1 if mode == "REE" else min(2, len(reference_names) - 1),
            key="rock_pattern_ref",
        )
        reference = NORMALIZATION_REFERENCES[ref_name]
        available = available_elements(wide, order, require_known_units=reference is not None)
        if len(available) >= 2:
            elements = st.multiselect("Элементы", list(order), default=available, key="rock_pattern_elements")
            pattern = prepare_pattern(wide, elements, reference)
            converted = [label for label in pattern.source_columns.values() if "→" in label]
            if converted:
                st.caption("Стехиометрические преобразования: " + "; ".join(converted))
            labels = wide["Rock"] if "Rock" in wide else None
            groups = wide["Massif"] if "Massif" in wide else None
            style = render_figure_style_controls(wide, key_prefix="rock_pattern")
            point_style = POINT_STYLE_PRESETS[style.point_style_name]
            fig = build_pattern_figure(
                pattern,
                labels=labels,
                group=groups,
                title=f"Whole-rock {mode}",
                ylabel="Sample / reference" if reference is not None else "Concentration",
                marker=point_style.markers[0],
                marker_size=max(2.0, style.marker_size / 14.0),
                alpha=point_style.alpha,
                linewidth=style.line_width,
                grid=style.grid,
                monochrome=style.monochrome,
                font_family=style.font_family,
                font_size=style.font_size,
                figure_size=(style.width_in, style.height_in),
            )
            st.pyplot(fig, width="stretch")
            _download_figure(fig, f"whole_rock_{mode}", style, "rock_pattern")
            plt.close(fig)
        else:
            st.info(
                "Недостаточно trace-element данных с известными единицами для нормированного pattern. "
                "Bare-колонки без единиц ПетроЛаб не считает ppm автоматически. K, P и Ti могут быть "
                "получены из K2O/P2O5/TiO2 wt.% с явным стехиометрическим пересчётом."
            )

    with tab_iso:
        isotopes = isotope_wide(project_id)
        numeric = [
            column for column in isotopes.columns
            if pd.to_numeric(isotopes[column], errors="coerce").notna().sum() >= 2
            and not str(column).startswith("_")
        ]
        if len(numeric) >= 2:
            x = st.selectbox("Изотопная X", numeric, key="rock_iso_x")
            y = st.selectbox("Изотопная Y", [column for column in numeric if column != x], key="rock_iso_y")
            l1, l2 = st.columns(2)
            x_label = l1.text_input("Подпись X", value=x, key="rock_iso_xlabel")
            y_label = l2.text_input("Подпись Y", value=y, key="rock_iso_ylabel")
            style = render_figure_style_controls(isotopes, key_prefix="rock_iso")
            fig = build_rock_scatter(
                isotopes,
                x,
                y,
                label_column="Rock" if style.label_points else None,
                title=f"{y} vs {x}",
                x_label=x_label,
                y_label=y_label,
                **_rock_scatter_style_kwargs(style),
            )
            st.pyplot(fig, width="stretch")
            _download_figure(fig, f"isotope_{y}_vs_{x}", style, "rock_iso")
            plt.close(fig)
        else:
            st.info("Добавьте как минимум две числовые изотопные величины у нескольких пород.")

    with tab_rhodes:
        all_links = [int(value) for value in list_mineral_links(int(selected_rock["id"]))]
        if not all_links:
            st.info("Свяжите породу с минералогическим dataset.")
            return
        accessible_links = [
            dataset_id for dataset_id in all_links
            if dataset_is_accessible(int(selected_rock["project_id"]), dataset_id)
        ]
        inaccessible_links = sorted(set(all_links) - set(accessible_links))
        if inaccessible_links:
            st.warning(
                "Rhodes не использует datasets, которые больше не подключены к текущему проекту: "
                + ", ".join(map(str, inaccessible_links[:8]))
            )
        if not accessible_links:
            st.info("Связанные mineral datasets сейчас недоступны в рабочем контексте проекта.")
            return
        minerals = load_unified_with_derived(int(selected_rock["project_id"]), accessible_links)
        olivine = minerals[minerals["Минерал"].astype(str).eq("olivine")].copy() if "Минерал" in minerals else pd.DataFrame()
        if olivine.empty or "Fo" not in olivine.columns:
            st.info("Для Rhodes нужен связанный набор оливинов с сохранённым Fo.")
            return
        comp = composition_dict(int(selected_rock["id"]))
        inferred_fe3 = inferred_whole_rock_fe3_fraction(comp)
        default_fe3 = float(inferred_fe3) if inferred_fe3 is not None else 0.0
        if inferred_fe3 is not None:
            st.caption(f"По раздельно заданному железу автоматически оценено Fe³⁺/ΣFe = {inferred_fe3:.3f}. Значение можно изменить вручную.")
        else:
            st.caption("Валентностное распределение total Fe не задано: Fe³⁺/ΣFe — пользовательское допущение для Mg# proxy.")
        fe3 = st.slider(
            "Доля Fe³⁺ в total Fe породы для Mg# proxy",
            0.0, 1.0, default_fe3, 0.01,
            key=f"rock_rhodes_fe3_{int(selected_rock['id'])}",
        )
        mgnum = whole_rock_mg_number(comp, fe3_fraction=fe3)
        if pd.isna(mgnum):
            st.warning("Невозможно рассчитать whole-rock Mg#: нужны MgO и FeO/FeOt/Fe2O3/Fe2O3t.")
            return
        rock_row = pd.DataFrame([{"Rock": selected_rock["name"], "Mg#_rock": mgnum}])
        style = render_figure_style_controls(olivine, key_prefix="rock_rhodes")
        fig = build_rhodes_figure(rock_row, olivine, **_rock_scatter_style_kwargs(style))
        st.pyplot(fig, width="stretch")
        _download_figure(fig, "rhodes_olivine_rock", style, "rock_rhodes")
        kd = measured_olivine_kd(olivine["Fo"], mgnum)
        view_columns = [column for column in ["Sample", "Grain", "Point", "Fo"] if column in olivine.columns]
        kd_table = olivine[view_columns].copy()
        kd_table["Kd_FeMg_ol-rock_proxy"] = kd.to_numpy()
        st.dataframe(kd_table, width="stretch", hide_index=True, height=320)
        st.caption(
            "Rhodes-style screening использует Kd-линии 0.27/0.30/0.33 вокруг классического "
            "оливин–жидкость Fe–Mg обмена. Whole-rock состав не всегда равен составу расплава: "
            "особая осторожность нужна для кумулятов, ксенокристов, контаминированных лампрофиров и кимберлитов."
        )
        plt.close(fig)
