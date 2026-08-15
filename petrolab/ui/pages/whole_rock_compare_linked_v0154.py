"""Добавить связанную интерактивную мультипанель к актуальному whole-rock сравнению."""
from __future__ import annotations

import streamlit as st

from petrolab.rock_comparison import whole_rock_comparison_dataframe
from petrolab.ui.project_context import active_project
from petrolab.ui.rock_linked_panels import render_rock_linked_multi_panel

from . import whole_rock_compare as _base


def render_whole_rock_compare_page() -> None:
    """Сохранить все существующие whole-rock диаграммы и добавить общий интерактивный отбор."""
    _base.render_whole_rock_compare_page()

    project = active_project()
    if project is None:
        return
    project_id = int(project["id"])
    dataframe = whole_rock_comparison_dataframe(project_id)
    if dataframe.empty:
        return

    st.divider()
    render_rock_linked_multi_panel(dataframe, project_id)
