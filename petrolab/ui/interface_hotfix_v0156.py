"""Укрепление геометрии desktop-интерфейса для ветки 0.15.6.

Здесь меняется только оболочка приложения: боковая панель, поиск и служебные
заголовки. Научные таблицы, графики и плотные рабочие панели сохраняют свою
обычную компактность.

Ключевой принцип hotfix: размер задаётся не только внутреннему тексту, но и
внешнему ``stElementContainer`` Streamlit. Иначе браузер мог отрисовать текст
выше контейнера, а следующий контрол начинал занимать ту же вертикальную область.
"""
from __future__ import annotations

import streamlit as st


CSS = r"""
<style>
/*
 * Не заставляем внутренние надписи создавать отступы через margin: такие
 * margin могут схлопываться на границе markdown-контейнера. Пространство между
 * строками задаётся внешним stElementContainer ниже.
 */
.petrolab-sidebar-brand-block {
    display: block !important;
    position: relative !important;
    box-sizing: border-box !important;
    min-height: 2.75rem !important;
    margin: 0 !important;
    padding: .06rem 0 .14rem !important;
}
.petrolab-sidebar-brand {
    display: block !important;
    position: relative !important;
    box-sizing: border-box !important;
    font-size: 1.08rem !important;
    font-weight: 750 !important;
    line-height: 1.25 !important;
    min-height: 1.36rem !important;
    margin: 0 !important;
    padding: 0 !important;
}
.petrolab-sidebar-version {
    display: block !important;
    position: relative !important;
    box-sizing: border-box !important;
    font-size: .76rem !important;
    line-height: 1.3 !important;
    min-height: 1rem !important;
    margin: .10rem 0 0 !important;
    padding: 0 !important;
}
.petrolab-nav-section {
    display: block !important;
    position: relative !important;
    box-sizing: border-box !important;
    clear: both !important;
    font-size: .70rem !important;
    line-height: 1.3 !important;
    min-height: .95rem !important;
    margin: 0 !important;
    padding: 0 !important;
}

/*
 * Streamlit 1.60 размещает элементы sidebar во внешних stElementContainer.
 * Именно эти контейнеры участвуют в вертикальном flex-потоке. Раньше текст
 * бренда/секций становился выше контейнера и визуально заходил на следующий
 * элемент. Теперь внешний контейнер всегда резервирует фактическую высоту.
 */
[data-testid="stSidebar"] [data-testid="stElementContainer"],
[data-testid="stSidebar"] .stElementContainer {
    flex-shrink: 0 !important;
    min-width: 0 !important;
}
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.petrolab-sidebar-brand-block),
[data-testid="stSidebar"] .stElementContainer:has(.petrolab-sidebar-brand-block) {
    min-height: 3.05rem !important;
    padding: .08rem 0 .18rem !important;
    margin: 0 !important;
    overflow: visible !important;
}
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.petrolab-nav-section),
[data-testid="stSidebar"] .stElementContainer:has(.petrolab-nav-section) {
    min-height: 1.48rem !important;
    padding: .30rem 0 .18rem !important;
    margin: 0 !important;
    overflow: visible !important;
}

/* Общий вертикальный поток остаётся компактным, но не сжимает детей. */
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    gap: .30rem !important;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] > div {
    flex-shrink: 0 !important;
}

/* Каждая кнопка занимает собственную строку, без отрицательных отступов. */
[data-testid="stSidebar"] .stButton {
    display: block !important;
    position: relative !important;
    box-sizing: border-box !important;
    margin: 0 !important;
    padding: 0 !important;
}
[data-testid="stSidebar"] .stButton > button {
    position: relative !important;
    box-sizing: border-box !important;
    min-height: 2.22rem !important;
    height: auto !important;
    padding: .40rem .56rem !important;
    margin: 0 !important;
    overflow: hidden !important;
}
[data-testid="stSidebar"] .stButton > button p {
    margin: 0 !important;
    font-size: .87rem !important;
    line-height: 1.28 !important;
}

/* Поиск и выбор проекта получают устойчивую высоту внешнего элемента. */
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stTextInput"]),
[data-testid="stSidebar"] .stElementContainer:has([data-testid="stTextInput"]) {
    min-height: 2.52rem !important;
    margin: 0 !important;
    padding: 0 !important;
}
[data-testid="stSidebar"] [data-testid="stElementContainer"]:has([data-testid="stSelectbox"]),
[data-testid="stSidebar"] .stElementContainer:has([data-testid="stSelectbox"]) {
    min-height: 2.52rem !important;
    margin: 0 !important;
    padding: 0 !important;
}
[data-testid="stSidebar"] [data-testid="stTextInput"] {
    display: block !important;
    position: relative !important;
    box-sizing: border-box !important;
    clear: both !important;
    margin: 0 !important;
    min-height: 2.42rem !important;
}
[data-testid="stSidebar"] [data-testid="stTextInput"] input {
    min-height: 2.36rem !important;
    height: 2.36rem !important;
    padding: .42rem .62rem !important;
    font-size: .85rem !important;
    line-height: 1.25 !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] {
    display: block !important;
    position: relative !important;
    box-sizing: border-box !important;
    clear: both !important;
    margin: 0 !important;
    min-height: 2.42rem !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] {
    position: relative !important;
    clear: both !important;
    margin-top: .12rem !important;
}

/*
 * Старый Unicode-символ информации зависел от установленного Windows-шрифта.
 * Рисуем окружность CSS-ом, внутри оставляем обычную латинскую i.
 */
.petrolab-info-dot {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    box-sizing: border-box !important;
    width: 1rem !important;
    min-width: 1rem !important;
    height: 1rem !important;
    border: 1px solid currentColor !important;
    border-radius: 50% !important;
    font-family: "Segoe UI", Arial, sans-serif !important;
    font-size: .68rem !important;
    font-weight: 700 !important;
    font-style: normal !important;
    line-height: 1 !important;
}
.petrolab-page-help > summary,
.petrolab-inline-help > summary,
.petrolab-section-help > summary {
    display: inline-flex !important;
    align-items: center !important;
    justify-content: center !important;
    min-width: 1.1rem !important;
    min-height: 1.1rem !important;
}
.petrolab-page-title-row,
.petrolab-section-title-wrap {
    flex-wrap: wrap !important;
    row-gap: .24rem !important;
}

/*
 * В коротком desktop-окне sidebar должен прокручиваться. Ничего внутри него
 * не уменьшается по высоте ради того, чтобы любой ценой поместиться на экран.
 */
@media (max-height: 620px) and (min-width: 761px) {
    [data-testid="stSidebar"] > div,
    [data-testid="stSidebar"] section {
        overflow-y: auto !important;
        overflow-x: hidden !important;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: .26rem !important;
    }
    [data-testid="stSidebar"] .stButton > button {
        min-height: 2.12rem !important;
        padding-top: .34rem !important;
        padding-bottom: .34rem !important;
    }
}

/* На пустом стартовом экране единственное действие не растягиваем на холст. */
.petrolab-page-header + div[data-testid="stAlert"] {
    max-width: 44rem;
}

/* Служебный текст компактный, но читаемый. */
[data-testid="stCaptionContainer"] {
    font-size: .76rem !important;
    line-height: 1.4 !important;
}
</style>
"""


def apply_interface_hotfix() -> None:
    """Подключить защитные CSS-правила оболочки PetroLab."""
    st.markdown(CSS, unsafe_allow_html=True)
