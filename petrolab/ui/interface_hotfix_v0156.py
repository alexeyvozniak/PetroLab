"""Desktop interface hardening for the 0.15.6 line.

These overrides deliberately target the application shell only.  Scientific tables,
plots and dense workbench controls keep their normal compact sizing, while the
sidebar/search/header chrome gets explicit geometry so browser zoom, short windows
and Windows text metrics cannot make adjacent controls overlap.
"""
from __future__ import annotations

import streamlit as st


CSS = r"""
<style>
/* Brand/version are separate rows with explicit line boxes. */
.petrolab-sidebar-brand {
    display: block !important;
    position: relative !important;
    font-size: 1.16rem !important;
    line-height: 1.32 !important;
    min-height: 1.5rem !important;
    margin: 0 !important;
    padding: .08rem 0 0 !important;
}
.petrolab-sidebar-version {
    display: block !important;
    position: relative !important;
    font-size: .74rem !important;
    line-height: 1.35 !important;
    min-height: 1rem !important;
    margin: .06rem 0 .48rem !important;
}
.petrolab-nav-section {
    display: block !important;
    position: relative !important;
    clear: both !important;
    font-size: .69rem !important;
    line-height: 1.4 !important;
    min-height: 1rem !important;
    margin: .62rem 0 .14rem !important;
    padding: 0 !important;
}

/* Give every sidebar control its own stable vertical box. */
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    gap: .28rem !important;
}
[data-testid="stSidebar"] .stButton {
    display: block !important;
    position: relative !important;
    margin: 0 !important;
}
[data-testid="stSidebar"] .stButton > button {
    position: relative !important;
    min-height: 2.18rem !important;
    height: auto !important;
    padding: .38rem .54rem !important;
    margin: 0 !important;
    overflow: hidden !important;
}
[data-testid="stSidebar"] .stButton > button p {
    margin: 0 !important;
    font-size: .86rem !important;
    line-height: 1.32 !important;
}

/* Search used to be particularly sensitive to short windows/browser scaling. */
[data-testid="stSidebar"] [data-testid="stTextInput"] {
    display: block !important;
    position: relative !important;
    clear: both !important;
    margin: .06rem 0 .12rem !important;
    min-height: 2.35rem !important;
}
[data-testid="stSidebar"] [data-testid="stTextInput"] input {
    min-height: 2.32rem !important;
    height: 2.32rem !important;
    padding: .42rem .62rem !important;
    font-size: .84rem !important;
    line-height: 1.25 !important;
}
[data-testid="stSidebar"] [data-testid="stSelectbox"] {
    display: block !important;
    position: relative !important;
    clear: both !important;
    margin: .04rem 0 .08rem !important;
}
[data-testid="stSidebar"] [data-testid="stExpander"] {
    position: relative !important;
    clear: both !important;
    margin-top: .18rem !important;
}

/* The old circled-Unicode glyph rendered differently across Windows fonts.
   Draw the information mark ourselves instead. */
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

/* On short desktop windows the sidebar must scroll, not compress its children. */
@media (max-height: 620px) and (min-width: 761px) {
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
        gap: .22rem !important;
    }
    .petrolab-sidebar-version {
        margin-bottom: .34rem !important;
    }
    .petrolab-nav-section {
        margin-top: .48rem !important;
    }
    [data-testid="stSidebar"] .stButton > button {
        min-height: 2.06rem !important;
        padding-top: .32rem !important;
        padding-bottom: .32rem !important;
    }
}

/* On an empty start screen, don't stretch the only action across the canvas. */
.petrolab-page-header + div[data-testid="stAlert"] {
    max-width: 44rem;
}

/* Service text is compact, but not microscopic. */
[data-testid="stCaptionContainer"] {
    font-size: .76rem !important;
    line-height: 1.4 !important;
}
</style>
"""


def apply_interface_hotfix() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
