from __future__ import annotations

import streamlit as st


CSS = r"""
<style>
:root {
    --petro-bg: #edf0ef;
    --petro-surface: #fbfcfb;
    --petro-surface-soft: #f1f3f2;
    --petro-surface-strong: #e5e9e7;
    --petro-text: #17211f;
    --petro-text-muted: #596663;
    --petro-border: #cbd2cf;
    --petro-border-strong: #aeb9b5;
    --petro-accent: #315f56;
    --petro-accent-hover: #244b44;
    --petro-accent-soft: #dfe9e6;
    --petro-success: #2f654c;
    --petro-success-soft: #e1ece6;
    --petro-warning: #775817;
    --petro-warning-soft: #f1ead7;
    --petro-danger: #8f3f3f;
    --petro-danger-soft: #f2e3e3;
    --petro-radius-sm: 4px;
    --petro-radius-md: 6px;
    --petro-radius-lg: 8px;
    --petro-radius-xl: 10px;
    --petro-shadow-soft: 0 1px 2px rgba(23,33,31,.055);
}

html, body, [class*="css"], [data-testid="stAppViewContainer"] {
    font-family: "Segoe UI", Arial, sans-serif;
    color: var(--petro-text);
}
body {
    font-weight: 500;
}
[data-testid="stAppViewContainer"] {
    background: var(--petro-bg);
}
[data-testid="stHeader"] {
    background: var(--petro-bg);
    border-bottom: 1px solid rgba(174,185,181,.55);
}
.block-container {
    padding-top: .85rem;
    padding-bottom: 2.5rem;
    max-width: 1760px;
}

h1, h2, h3 {
    letter-spacing: -.012em;
    color: var(--petro-text);
    font-family: "Segoe UI", Arial, sans-serif;
}
h1 {
    font-size: clamp(1.45rem, 1.75vw, 1.72rem);
    line-height: 1.16;
    font-weight: 750;
    margin-bottom: .18rem;
}
h2 {
    font-size: 1.12rem;
    line-height: 1.25;
    font-weight: 700;
    margin-top: 1.15rem;
}
h3 {
    font-size: .98rem;
    line-height: 1.3;
    font-weight: 700;
}

.petrolab-page-header {
    position: relative;
    margin: 0 0 .8rem;
    padding: .15rem 0 .68rem;
    max-width: none;
    border-bottom: 1px solid var(--petro-border);
}
.petrolab-eyebrow {
    color: var(--petro-text-muted);
    font-size: .66rem;
    font-weight: 750;
    letter-spacing: .07em;
    text-transform: uppercase;
    margin-bottom: .16rem;
}
.petrolab-page-title-row {
    display: flex;
    align-items: center;
    gap: .4rem;
    min-width: 0;
}
.petrolab-page-title {
    color: var(--petro-text);
    font-size: clamp(1.45rem, 1.75vw, 1.72rem);
    line-height: 1.16;
    font-weight: 750;
    letter-spacing: -.016em;
    margin: 0;
}
.petrolab-page-lead {
    color: var(--petro-text-muted);
    font-size: .83rem;
    line-height: 1.45;
    max-width: 64rem;
}
.petrolab-context-line {
    color: var(--petro-text-muted);
    font-size: .76rem;
    font-weight: 600;
    margin-top: .2rem;
}
.petrolab-page-help,
.petrolab-inline-help,
.petrolab-section-help {
    position: relative;
    display: inline-block;
}
.petrolab-page-help > summary,
.petrolab-inline-help > summary,
.petrolab-section-help > summary {
    list-style: none;
    cursor: pointer;
    user-select: none;
    color: var(--petro-text-muted);
    font-size: .76rem;
    font-weight: 700;
    line-height: 1;
}
.petrolab-page-help > summary::-webkit-details-marker,
.petrolab-inline-help > summary::-webkit-details-marker,
.petrolab-section-help > summary::-webkit-details-marker { display: none; }
.petrolab-page-help[open] > div,
.petrolab-inline-help[open] > div,
.petrolab-section-help[open] > div {
    position: absolute;
    z-index: 1000;
    top: 1.25rem;
    left: 0;
    width: min(32rem, 70vw);
    padding: .62rem .72rem;
    border: 1px solid var(--petro-border-strong);
    border-radius: var(--petro-radius-md);
    background: var(--petro-surface);
    box-shadow: 0 8px 24px rgba(23,33,31,.12);
    color: var(--petro-text);
    font-size: .78rem;
    font-weight: 500;
    line-height: 1.45;
}
.petrolab-inline-help {
    margin: .08rem 0 .28rem;
}
.petrolab-inline-help[open] > div {
    position: relative;
    top: .25rem;
    width: min(52rem, 100%);
    box-shadow: none;
    background: var(--petro-surface-soft);
}
.petrolab-section-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: .6rem;
    margin: .9rem 0 .42rem;
    padding-bottom: .28rem;
    border-bottom: 1px solid var(--petro-border);
}
.petrolab-section-title-wrap {
    display: flex;
    align-items: center;
    gap: .35rem;
    min-width: 0;
}
.petrolab-section-title {
    font-weight: 700;
    font-size: .96rem;
    line-height: 1.3;
    letter-spacing: -.005em;
    margin: 0;
}
.petrolab-section-note {
    color: var(--petro-text-muted);
    font-size: .76rem;
    font-weight: 500;
}
.petrolab-reading-width { max-width: 920px; }

[data-testid="stMetric"] {
    border: 1px solid var(--petro-border);
    padding: .58rem .72rem;
    border-radius: var(--petro-radius-md);
    background: var(--petro-surface);
    box-shadow: none;
}
[data-testid="stMetricLabel"] {
    color: var(--petro-text-muted);
    font-size: .75rem;
    font-weight: 650;
}
[data-testid="stMetricValue"] {
    color: var(--petro-text);
    letter-spacing: -.015em;
    font-weight: 700;
}

.petrolab-card {
    border: 1px solid var(--petro-border);
    border-radius: var(--petro-radius-md);
    padding: .72rem .82rem;
    margin-bottom: .52rem;
    background: var(--petro-surface);
    box-shadow: none;
}
.petrolab-card-soft {
    border: 1px solid var(--petro-border);
    border-radius: var(--petro-radius-md);
    padding: .68rem .78rem;
    background: var(--petro-surface-soft);
}
.petrolab-card-active {
    border-color: var(--petro-accent);
    box-shadow: inset 3px 0 0 var(--petro-accent);
}
.petrolab-card-title {
    font-weight: 700;
    margin-bottom: .12rem;
}
.petrolab-card-meta,
.petrolab-muted {
    color: var(--petro-text-muted);
    font-size: .78rem;
    line-height: 1.4;
}
.petrolab-big-number {
    font-size: 1.4rem;
    font-weight: 750;
    letter-spacing: -.02em;
    line-height: 1.05;
}

.petrolab-badges {
    display: flex;
    flex-wrap: wrap;
    gap: .28rem;
    margin: .2rem 0 .42rem;
}
.petrolab-badge {
    display: inline-flex;
    align-items: center;
    gap: .22rem;
    padding: .17rem .4rem;
    border-radius: 3px;
    font-size: .69rem;
    font-weight: 650;
    border: 1px solid var(--petro-border);
    background: var(--petro-surface-soft);
    color: var(--petro-text-muted);
}
.petrolab-badge.accent { background: var(--petro-accent-soft); border-color: #b9cbc6; color: var(--petro-accent-hover); }
.petrolab-badge.success { background: var(--petro-success-soft); border-color: #bfd3c7; color: var(--petro-success); }
.petrolab-badge.warning { background: var(--petro-warning-soft); border-color: #dfd0a8; color: var(--petro-warning); }
.petrolab-badge.danger { background: var(--petro-danger-soft); border-color: #dfbebe; color: var(--petro-danger); }

.petrolab-toolbar {
    border: 1px solid var(--petro-border-strong);
    border-radius: var(--petro-radius-md);
    background: var(--petro-surface-strong);
    padding: .48rem .55rem;
    margin: .2rem 0 .55rem;
    box-shadow: none;
}
.petrolab-workspace {
    border: 1px solid var(--petro-border-strong);
    border-radius: var(--petro-radius-lg);
    background: var(--petro-surface);
    padding: .62rem;
    box-shadow: none;
}
.petrolab-export-zone {
    border-top: 1px solid var(--petro-border);
    margin-top: .7rem;
    padding-top: .58rem;
}
.petrolab-danger-zone {
    border: 1px solid #d9b4b4;
    background: var(--petro-danger-soft);
    border-radius: var(--petro-radius-md);
    padding: .62rem .72rem;
}

[data-testid="stSidebar"] {
    border-right: 1px solid var(--petro-border-strong);
    background: #e6eae8;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .22rem; }
.petrolab-sidebar-brand {
    font-size: 1.08rem;
    font-weight: 750;
    letter-spacing: -.012em;
    margin: .12rem 0 .02rem;
}
.petrolab-sidebar-version {
    color: var(--petro-text-muted);
    font-size: .68rem;
    margin-bottom: .42rem;
}
.petrolab-nav-section {
    color: #46514e;
    font-size: .63rem;
    font-weight: 750;
    letter-spacing: .07em;
    text-transform: uppercase;
    margin: .58rem 0 .1rem;
}
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    justify-content: flex-start;
    min-height: 1.88rem;
    padding: .28rem .46rem;
    border-radius: 3px;
    border-color: transparent;
    background: transparent;
    box-shadow: none;
    font-weight: 600;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(49,95,86,.08);
    border-color: transparent;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
    background: #d9e3e0 !important;
    color: var(--petro-accent-hover) !important;
    border-color: #b9c7c3 !important;
    border-left: 3px solid var(--petro-accent) !important;
    font-weight: 700;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] p,
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] p { color: var(--petro-accent-hover) !important; }

[data-testid="stExpander"] {
    border-radius: var(--petro-radius-md);
    border-color: var(--petro-border);
    background: var(--petro-surface);
}
[data-testid="stExpander"] summary { font-weight: 650; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border-radius: 3px;
    overflow: hidden;
    border: 1px solid var(--petro-border-strong);
    background: var(--petro-surface);
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: 0;
    overflow-x: auto;
    border: 1px solid var(--petro-border-strong);
    border-radius: var(--petro-radius-sm) var(--petro-radius-sm) 0 0;
    background: var(--petro-surface-strong);
    padding: 0 .18rem;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    white-space: nowrap;
    min-height: 2.2rem;
    padding: .28rem .7rem;
    border-radius: 0;
    font-weight: 650;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background: var(--petro-surface);
    font-weight: 750;
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { height: 2px; }

.stButton > button, .stDownloadButton > button {
    border-radius: var(--petro-radius-sm);
    min-height: 2.14rem;
    font-weight: 650;
    box-shadow: none;
}
.stButton > button[kind="primary"] {
    background: var(--petro-accent);
    border-color: var(--petro-accent);
}
.stButton > button[kind="primary"]:hover {
    background: var(--petro-accent-hover);
    border-color: var(--petro-accent-hover);
}
[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
textarea,
input {
    border-radius: var(--petro-radius-sm) !important;
}
[data-testid="stCaptionContainer"] {
    color: var(--petro-text-muted);
    font-size: .73rem;
    line-height: 1.35;
}
[data-testid="stAlert"] {
    border-radius: var(--petro-radius-sm);
    padding-top: .45rem;
    padding-bottom: .45rem;
}

button:focus-visible,
input:focus-visible,
textarea:focus-visible,
[role="combobox"]:focus-visible,
[role="radio"]:focus-visible {
    outline: 2px solid var(--petro-accent) !important;
    outline-offset: 2px !important;
}

@media (max-width: 1100px) {
    .block-container { padding-left: .78rem; padding-right: .78rem; }
    [data-testid="column"] { min-width: 0 !important; }
}
@media (max-width: 760px) {
    .block-container { padding-left: .55rem; padding-right: .55rem; padding-top: .55rem; }
    h1, .petrolab-page-title { font-size: 1.38rem; }
    h2 { font-size: 1.04rem; }
    .petrolab-section-header {
        align-items: flex-start;
        margin: .8rem 0 .38rem;
    }
    .petrolab-section-title { font-size: .96rem; }
    .petrolab-section-note { font-size: .72rem; line-height: 1.35; }
    .petrolab-workspace { padding: .5rem; border-radius: var(--petro-radius-md); }
    .petrolab-card { padding: .62rem .68rem; }
    .stButton > button, .stDownloadButton > button { min-height: 2.45rem; }
    .petrolab-page-help[open] > div { left: auto; right: 0; width: min(27rem, 86vw); }
}
</style>
"""


def apply_theme(ui_density: str = "comfortable") -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if ui_density == "compact":
        st.markdown(
            """
            <style>
            .block-container { max-width: 1840px; }
            [data-testid="stVerticalBlock"] { gap: .42rem; }
            [data-testid="stMetric"] { padding: .48rem .62rem; }
            .petrolab-card { padding: .58rem .66rem; margin-bottom: .4rem; }
            .petrolab-page-header { margin-bottom: .62rem; }
            </style>
            """,
            unsafe_allow_html=True,
        )
