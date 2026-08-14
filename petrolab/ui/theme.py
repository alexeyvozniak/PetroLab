from __future__ import annotations

import streamlit as st


CSS = r"""
<style>
:root {
    --petro-bg: #f6f8f7;
    --petro-surface: #ffffff;
    --petro-surface-soft: #eef3f1;
    --petro-text: #1f2927;
    --petro-text-muted: #596663;
    --petro-border: #dce4e1;
    --petro-border-strong: #c9d5d1;
    --petro-accent: #486d65;
    --petro-accent-hover: #3c5e57;
    --petro-accent-soft: #e4eeeb;
    --petro-success: #3e7058;
    --petro-success-soft: #e8f2ed;
    --petro-warning: #8a6827;
    --petro-warning-soft: #f7f0df;
    --petro-danger: #a34d4d;
    --petro-danger-soft: #f8eaea;
    --petro-radius-sm: 8px;
    --petro-radius-md: 12px;
    --petro-radius-lg: 16px;
    --petro-radius-xl: 20px;
    --petro-shadow-soft: 0 1px 2px rgba(31,41,39,.035), 0 6px 20px rgba(31,41,39,.025);
}

html, body, [class*="css"] {
    color: var(--petro-text);
}
[data-testid="stAppViewContainer"] {
    background: var(--petro-bg);
}
[data-testid="stHeader"] {
    background: rgba(246,248,247,.88);
    backdrop-filter: blur(10px);
}
.block-container {
    padding-top: 1.25rem;
    padding-bottom: 4rem;
    max-width: 1540px;
}

h1, h2, h3 {
    letter-spacing: -0.025em;
    color: var(--petro-text);
}
h1 {
    font-size: clamp(1.8rem, 2.3vw, 2.15rem);
    line-height: 1.12;
    font-weight: 650;
    margin-bottom: .28rem;
}
h2 {
    font-size: 1.34rem;
    line-height: 1.25;
    font-weight: 620;
    margin-top: 1.65rem;
}
h3 {
    font-size: 1.08rem;
    line-height: 1.3;
    font-weight: 620;
}

.petrolab-page-header {
    margin: .1rem 0 1.35rem;
    max-width: 76rem;
}
.petrolab-eyebrow {
    color: var(--petro-accent);
    font-size: .74rem;
    font-weight: 700;
    letter-spacing: .08em;
    text-transform: uppercase;
    margin-bottom: .28rem;
}
.petrolab-page-title {
    color: var(--petro-text);
    font-size: clamp(1.8rem, 2.3vw, 2.15rem);
    line-height: 1.12;
    font-weight: 650;
    letter-spacing: -.03em;
    margin: 0 0 .35rem;
}
.petrolab-page-lead {
    color: var(--petro-text-muted);
    font-size: .96rem;
    line-height: 1.55;
    max-width: 72rem;
}
.petrolab-context-line {
    color: var(--petro-text-muted);
    font-size: .82rem;
    margin-top: .35rem;
}
.petrolab-section-header {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 1rem;
    margin: 1.4rem 0 .7rem;
}
.petrolab-section-title {
    font-weight: 650;
    font-size: 1.03rem;
    line-height: 1.3;
    letter-spacing: -.015em;
    margin: 0;
}
.petrolab-section-note {
    color: var(--petro-text-muted);
    font-size: .82rem;
}
.petrolab-reading-width {
    max-width: 920px;
}

[data-testid="stMetric"] {
    border: 1px solid var(--petro-border);
    padding: .82rem 1rem;
    border-radius: var(--petro-radius-lg);
    background: var(--petro-surface);
    box-shadow: var(--petro-shadow-soft);
}
[data-testid="stMetricLabel"] {
    color: var(--petro-text-muted);
}
[data-testid="stMetricValue"] {
    color: var(--petro-text);
    letter-spacing: -.025em;
}

.petrolab-card {
    border: 1px solid var(--petro-border);
    border-radius: var(--petro-radius-lg);
    padding: 1rem 1.1rem;
    margin-bottom: .8rem;
    background: var(--petro-surface);
    box-shadow: var(--petro-shadow-soft);
}
.petrolab-card-soft {
    border: 1px solid var(--petro-border);
    border-radius: var(--petro-radius-lg);
    padding: .9rem 1rem;
    background: var(--petro-surface-soft);
}
.petrolab-card-active {
    border: 1px solid var(--petro-accent);
    box-shadow: 0 0 0 2px var(--petro-accent-soft);
}
.petrolab-card-title {
    font-weight: 650;
    margin-bottom: .18rem;
}
.petrolab-card-meta,
.petrolab-muted {
    color: var(--petro-text-muted);
    font-size: .86rem;
    line-height: 1.45;
}
.petrolab-big-number {
    font-size: 1.65rem;
    font-weight: 650;
    letter-spacing: -.035em;
    line-height: 1.05;
}

.petrolab-badges {
    display: flex;
    flex-wrap: wrap;
    gap: .35rem;
    margin: .3rem 0 .55rem;
}
.petrolab-badge {
    display: inline-flex;
    align-items: center;
    gap: .28rem;
    padding: .22rem .5rem;
    border-radius: 999px;
    font-size: .75rem;
    font-weight: 600;
    border: 1px solid var(--petro-border);
    background: var(--petro-surface-soft);
    color: var(--petro-text-muted);
}
.petrolab-badge.accent { background: var(--petro-accent-soft); border-color: #c9dcd6; color: var(--petro-accent-hover); }
.petrolab-badge.success { background: var(--petro-success-soft); border-color: #cce0d4; color: var(--petro-success); }
.petrolab-badge.warning { background: var(--petro-warning-soft); border-color: #eadcb9; color: var(--petro-warning); }
.petrolab-badge.danger { background: var(--petro-danger-soft); border-color: #ebcccc; color: var(--petro-danger); }

.petrolab-toolbar {
    border: 1px solid var(--petro-border);
    border-radius: var(--petro-radius-lg);
    background: var(--petro-surface);
    padding: .65rem .75rem;
    margin: .25rem 0 .75rem;
    box-shadow: var(--petro-shadow-soft);
}
.petrolab-workspace {
    border: 1px solid var(--petro-border);
    border-radius: var(--petro-radius-xl);
    background: var(--petro-surface);
    padding: .9rem;
    box-shadow: var(--petro-shadow-soft);
}
.petrolab-export-zone {
    border-top: 1px solid var(--petro-border);
    margin-top: 1rem;
    padding-top: .85rem;
}
.petrolab-danger-zone {
    border: 1px solid #ebcccc;
    background: var(--petro-danger-soft);
    border-radius: var(--petro-radius-lg);
    padding: .85rem 1rem;
}

[data-testid="stSidebar"] {
    border-right: 1px solid var(--petro-border);
    background: #f2f5f4;
}
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
    gap: .38rem;
}
.petrolab-sidebar-brand {
    font-size: 1.2rem;
    font-weight: 700;
    letter-spacing: -.025em;
    margin: .15rem 0 .05rem;
}
.petrolab-sidebar-version {
    color: var(--petro-text-muted);
    font-size: .75rem;
    margin-bottom: .65rem;
}
.petrolab-nav-section {
    color: var(--petro-text-muted);
    font-size: .68rem;
    font-weight: 750;
    letter-spacing: .09em;
    text-transform: uppercase;
    margin: .75rem 0 .15rem;
}
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    justify-content: flex-start;
    min-height: 2rem;
    padding: .35rem .6rem;
    border-radius: var(--petro-radius-sm);
    border-color: transparent;
    background: transparent;
    box-shadow: none;
}
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(72,109,101,.08);
    border-color: transparent;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
    background: var(--petro-accent-soft) !important;
    color: var(--petro-accent-hover) !important;
    border-color: #c9dcd6 !important;
    font-weight: 650;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] p,
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] p {
    color: var(--petro-accent-hover) !important;
}

[data-testid="stExpander"] {
    border-radius: var(--petro-radius-md);
    border-color: var(--petro-border);
    background: rgba(255,255,255,.45);
}
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border-radius: var(--petro-radius-md);
    overflow: hidden;
    border: 1px solid var(--petro-border);
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: .15rem;
    overflow-x: auto;
    border-bottom-color: var(--petro-border);
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    white-space: nowrap;
}

.stButton > button, .stDownloadButton > button {
    border-radius: 10px;
    min-height: 2.4rem;
}
.stButton > button[kind="primary"] {
    background: var(--petro-accent);
    border-color: var(--petro-accent);
}
.stButton > button[kind="primary"]:hover {
    background: var(--petro-accent-hover);
    border-color: var(--petro-accent-hover);
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
    .block-container { padding-left: 1rem; padding-right: 1rem; }
    [data-testid="column"] { min-width: 0 !important; }
}
@media (max-width: 760px) {
    .block-container { padding-left: .7rem; padding-right: .7rem; padding-top: .75rem; }
    h1, .petrolab-page-title { font-size: 1.7rem; }
    h2 { font-size: 1.25rem; }
    .petrolab-section-header {
        flex-direction: column;
        align-items: flex-start;
        justify-content: flex-start;
        gap: .15rem;
        margin: 1.25rem 0 .65rem;
    }
    .petrolab-section-title,
    .petrolab-section-note {
        width: 100%;
        max-width: none;
    }
    .petrolab-section-title { font-size: 1.12rem; }
    .petrolab-section-note { font-size: .78rem; line-height: 1.4; }
    .petrolab-workspace { padding: .65rem; border-radius: var(--petro-radius-md); }
    .petrolab-card { padding: .8rem .85rem; }
    .stButton > button, .stDownloadButton > button { min-height: 2.65rem; }
}
</style>
"""


def apply_theme(ui_density: str = "comfortable") -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if ui_density == "compact":
        st.markdown(
            """
            <style>
            .block-container { max-width: 1700px; }
            [data-testid="stVerticalBlock"] { gap: .58rem; }
            [data-testid="stMetric"] { padding: .6rem .78rem; }
            .petrolab-card { padding: .78rem .9rem; margin-bottom: .55rem; }
            .petrolab-page-header { margin-bottom: .95rem; }
            </style>
            """,
            unsafe_allow_html=True,
        )
