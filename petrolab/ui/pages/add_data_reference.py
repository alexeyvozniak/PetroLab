from __future__ import annotations

import streamlit as st

from petrolab.ui import universal_intake_extensions
from petrolab.ui.intake_workflow import render_intake_workflow
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project
from petrolab.ui.source_sheet_image_wizard import render_source_sheet_image_wizard


def _light_sidebar_for_reference() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"], [data-testid="stSidebar"] > div:first-child {
            background:#ffffff !important; border-right:1px solid #dce3e8 !important;
        }
        [data-testid="stSidebar"] .petrolab-sidebar-brand { color:#0f7f82 !important; }
        [data-testid="stSidebar"] .petrolab-sidebar-version,
        [data-testid="stSidebar"] [data-testid="stCaptionContainer"],
        [data-testid="stSidebar"] .petrolab-nav-section { color:#7b8796 !important; }
        [data-testid="stSidebar"] .stButton > button {
            color:#425066 !important; background:transparent !important;
        }
        [data-testid="stSidebar"] .stButton > button:hover { background:#f3f7f8 !important; }
        [data-testid="stSidebar"] .stButton > button[kind="primary"],
        [data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
            color:#0f6e71 !important; background:#e9f5f4 !important;
            border-color:#c4dfdf !important; border-left:3px solid #0f7f82 !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] > div {
            background:#ffffff !important; border-color:#d5dde3 !important;
        }
        [data-testid="stSidebar"] [data-baseweb="select"] span,
        [data-testid="stSidebar"] [data-baseweb="select"] svg { color:#334155 !important; fill:#334155 !important; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_add_data_reference_page() -> None:
    _light_sidebar_for_reference()
    project = active_project()

    top = st.columns([2.1, 4.2, 1.1, .9, .9])
    top[0].markdown('<div class="pd-screen-title">Добавить данные</div>', unsafe_allow_html=True)
    top[1].text_input(
        "Поиск",
        placeholder="Поиск по проектам, образцам, минералам, точкам…",
        key="pd_add_data_search",
        label_visibility="collapsed",
    )
    top[2].button("Добавить", type="primary", width="stretch", key="pd_add_data_top")
    top[3].button("Справка", width="stretch", key="pd_add_data_help")
    top[4].button("Настройки", width="stretch", key="pd_add_data_settings", on_click=lambda: navigate("settings"))

    st.markdown('<div class="pd-panel-title">Проверка импорта</div>', unsafe_allow_html=True)
    st.markdown(
        """
        <div class="pd-status-strip">
          <div class="pd-status-item"><strong>1 · Файл</strong><span>Excel / CSV / изображения</span></div>
          <div class="pd-status-item"><strong>2 · Листы</strong><span>структура книги</span></div>
          <div class="pd-status-item"><strong>3 · Структура</strong><span>Sample · Mineral · Point</span></div>
          <div class="pd-status-item"><strong>4 · Поля</strong><span>сопоставление колонок</span></div>
          <div class="pd-status-item"><strong>5 · Сохранение</strong><span>только после проверки</span></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if project is None:
        st.markdown(
            '<div class="pd-note-card">Для импорта нужен активный проект. Создайте новый проект или выберите существующий.</div>',
            unsafe_allow_html=True,
        )
        if st.button("Открыть проекты", type="primary", key="pd_add_data_projects"):
            navigate("projects")
            st.rerun()
        return

    st.caption(f"Активный проект: {project['name']} · данные сначала проверяются, затем сохраняются одним явным действием")

    original_image_wizard = universal_intake_extensions.render_image_wizard_multi_dataset
    universal_intake_extensions.render_image_wizard_multi_dataset = render_source_sheet_image_wizard
    try:
        render_intake_workflow(int(project["id"]))
    finally:
        universal_intake_extensions.render_image_wizard_multi_dataset = original_image_wizard
