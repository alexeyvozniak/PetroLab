"""Небольшие визуальные исправления поверх темы 0.15.6.

Этот слой намеренно узкий: он не меняет научные виджеты и плотные таблицы,
а только возвращает нормальную читаемость навигации и базовых подписей после
перехода на новый desktop launcher.
"""
from __future__ import annotations

import streamlit as st


CSS = r"""
<style>
/* Боковая навигация не должна выглядеть как мелкая служебная подпись. */
.petrolab-sidebar-brand {
    font-size: 1.16rem !important;
    line-height: 1.15;
}
.petrolab-sidebar-version {
    font-size: .74rem !important;
    line-height: 1.25;
}
.petrolab-nav-section {
    font-size: .69rem !important;
    line-height: 1.25;
}
[data-testid="stSidebar"] .stButton > button {
    min-height: 2.08rem !important;
    padding: .34rem .52rem !important;
}
[data-testid="stSidebar"] .stButton > button p {
    font-size: .86rem !important;
    line-height: 1.25 !important;
}

/* На пустом стартовом экране не растягиваем единственное действие по всему полотну. */
.petrolab-page-header + div[data-testid="stAlert"] {
    max-width: 44rem;
}

/* Подписи и служебный текст остаются компактными, но не микроскопическими. */
[data-testid="stCaptionContainer"] {
    font-size: .76rem !important;
}
</style>
"""


def apply_interface_hotfix() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
