from __future__ import annotations

import streamlit as st

from petrolab.publication_composer import LABEL_MODE_TITLES, default_panel_label, panel_label_sequence

from . import multi_panel as _multi
from .v0151_wrappers import render_multi_panel_page as _render_v0151_multi_panel_page


def _panel_label_controls(panel_count: int) -> list[dict]:
    panel_count = max(2, min(6, int(panel_count)))
    mode_by_title = {title: key for key, title in LABEL_MODE_TITLES.items()}
    with st.expander("Метки панелей A/B/C · А/Б/В", expanded=False):
        c1, c2, c3 = st.columns([1.4, 1, 1.2])
        mode_title = c1.selectbox(
            "Автоматическая схема",
            list(mode_by_title),
            index=list(mode_by_title).index("A, B, C…") if "A, B, C…" in mode_by_title else 0,
            key="multi_panel_label_mode_v0152",
        )
        mode = mode_by_title[mode_title]
        show_all = c2.checkbox("Показывать", value=True, key="multi_panel_labels_global_v0152")
        reset = c3.button("Сбросить по схеме", key="multi_panel_labels_reset_v0152", width="stretch")
        auto = panel_label_sequence(panel_count, mode)
        if reset:
            for index, text in enumerate(auto):
                st.session_state[f"multi_panel_label_text_{index}"] = text
                st.session_state[f"multi_panel_label_enabled_{index}"] = bool(text)
                st.session_state[f"multi_panel_label_x_{index}"] = 0.025
                st.session_state[f"multi_panel_label_y_{index}"] = 0.975
                st.session_state[f"multi_panel_label_size_{index}"] = 11.0

        labels: list[dict] = []
        for index in range(panel_count):
            text_key = f"multi_panel_label_text_{index}"
            enabled_key = f"multi_panel_label_enabled_{index}"
            x_key = f"multi_panel_label_x_{index}"
            y_key = f"multi_panel_label_y_{index}"
            size_key = f"multi_panel_label_size_{index}"
            st.session_state.setdefault(text_key, auto[index])
            st.session_state.setdefault(enabled_key, bool(auto[index]))
            st.session_state.setdefault(x_key, 0.025)
            st.session_state.setdefault(y_key, 0.975)
            st.session_state.setdefault(size_key, 11.0)
            cols = st.columns([0.8, 1.4, 0.8, 0.8, 0.8])
            enabled = cols[0].checkbox(
                f"{index + 1}",
                key=enabled_key,
                help=f"Показывать метку панели {index + 1}",
            )
            text = cols[1].text_input(
                f"Текст {index + 1}",
                key=text_key,
                label_visibility="collapsed",
            )
            x = cols[2].number_input(
                f"X {index + 1}",
                min_value=-0.25,
                max_value=1.25,
                step=0.01,
                format="%.3f",
                key=x_key,
            )
            y = cols[3].number_input(
                f"Y {index + 1}",
                min_value=-0.25,
                max_value=1.25,
                step=0.01,
                format="%.3f",
                key=y_key,
            )
            size = cols[4].number_input(
                f"pt {index + 1}",
                min_value=4.0,
                max_value=40.0,
                step=0.5,
                key=size_key,
            )
            labels.append(default_panel_label(
                str(text),
                enabled=bool(show_all) and bool(enabled),
                x=float(x),
                y=float(y),
                font_size=float(size),
            ))
        st.caption(
            "Координаты X/Y нормированы внутри каждой панели. Ручной текст не меняется при переключении схемы, пока вы явно не нажмёте «Сбросить по схеме»."
        )
    return labels


def render_multi_panel_page() -> None:
    original_build = _multi.build_multi_panel_scatter
    original_section_header = _multi.render_section_header
    label_state: dict[str, list[dict]] = {}

    def section_header_with_labels(title: str, subtitle: str = "") -> None:
        original_section_header(title, subtitle)
        if title == "Панели":
            panel_count = int(st.session_state.get("multi_panel_count", 4) or 4)
            label_state["labels"] = _panel_label_controls(panel_count)

    def build_with_labels(dataframe, panels, **kwargs):
        labels = label_state.get("labels")
        if labels is None:
            labels = [
                default_panel_label(text)
                for text in panel_label_sequence(len(panels), "latin_upper")
            ]
        prepared: list[dict] = []
        for index, panel in enumerate(panels):
            item = dict(panel)
            if index < len(labels):
                item["panel_label"] = labels[index]
            prepared.append(item)
        return original_build(dataframe, prepared, **kwargs)

    _multi.render_section_header = section_header_with_labels
    _multi.build_multi_panel_scatter = build_with_labels
    try:
        _render_v0151_multi_panel_page()
    finally:
        _multi.render_section_header = original_section_header
        _multi.build_multi_panel_scatter = original_build
