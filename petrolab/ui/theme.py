from __future__ import annotations

import streamlit as st


CSS = r"""
<style>
:root {
    --petro-bg: #0a101b;
    --petro-surface: #101827;
    --petro-surface-soft: #141f31;
    --petro-surface-strong: #19263a;
    --petro-sidebar: #0d1522;
    --petro-text: #f4f7fb;
    --petro-text-muted: #91a1b7;
    --petro-text-dim: #6f8097;
    --petro-border: #233149;
    --petro-border-strong: #30415d;
    --petro-accent: #3b82f6;
    --petro-accent-hover: #5aa2ff;
    --petro-accent-soft: rgba(59,130,246,.16);
    --petro-accent-border: rgba(96,165,250,.42);
    --petro-success: #52d39a;
    --petro-success-soft: rgba(82,211,154,.12);
    --petro-warning: #f2bd57;
    --petro-warning-soft: rgba(242,189,87,.12);
    --petro-danger: #ff7f87;
    --petro-danger-soft: rgba(255,127,135,.12);
    --petro-radius-sm: 8px;
    --petro-radius-md: 10px;
    --petro-radius-lg: 12px;
    --petro-radius-xl: 14px;
    --petro-shadow-soft: 0 10px 30px rgba(0,0,0,.18);
}

html, body, [class*="css"], [data-testid="stAppViewContainer"] {
    font-family: "Segoe UI", Inter, Arial, sans-serif;
    color: var(--petro-text);
}
body { font-weight: 450; }
[data-testid="stAppViewContainer"] {
    background:
        radial-gradient(circle at 72% -12%, rgba(59,130,246,.08), transparent 28rem),
        var(--petro-bg);
}
[data-testid="stHeader"] {
    background: rgba(10,16,27,.92);
    border-bottom: 1px solid rgba(48,65,93,.58);
    backdrop-filter: blur(12px);
}
[data-testid="stToolbar"] { color: var(--petro-text-muted); }
.block-container {
    padding-top: 1.05rem;
    padding-bottom: 3rem;
    max-width: 1680px;
}

p, label, li, span { color: inherit; }
a { color: #79b7ff; }
h1, h2, h3 {
    letter-spacing: -.02em;
    color: var(--petro-text);
    font-family: "Segoe UI", Inter, Arial, sans-serif;
}
h1 {
    font-size: clamp(1.65rem, 2vw, 2rem);
    line-height: 1.12;
    font-weight: 760;
    margin-bottom: .22rem;
}
h2 {
    font-size: 1.18rem;
    line-height: 1.25;
    font-weight: 720;
    margin-top: 1.2rem;
}
h3 {
    font-size: 1rem;
    line-height: 1.3;
    font-weight: 700;
}

.petrolab-page-header {
    position: relative;
    margin: 0 0 1rem;
    padding: .2rem 0 .85rem;
    max-width: none;
    border-bottom: 1px solid var(--petro-border);
}
.petrolab-eyebrow {
    color: #77aef8;
    font-size: .65rem;
    font-weight: 760;
    letter-spacing: .1em;
    text-transform: uppercase;
    margin-bottom: .22rem;
}
.petrolab-page-title-row {
    display: flex;
    align-items: center;
    gap: .45rem;
    min-width: 0;
}
.petrolab-page-title {
    color: var(--petro-text);
    font-size: clamp(1.65rem, 2vw, 2rem);
    line-height: 1.12;
    font-weight: 760;
    letter-spacing: -.025em;
    margin: 0;
}
.petrolab-page-lead {
    color: var(--petro-text-muted);
    font-size: .86rem;
    line-height: 1.5;
    max-width: 68rem;
}
.petrolab-context-line {
    color: #b6c3d4;
    font-size: .76rem;
    font-weight: 620;
    margin-top: .28rem;
}
.petrolab-work-context {
    margin: .4rem 0 .72rem;
    padding: .55rem .72rem;
    border: 1px solid var(--petro-border);
    border-left: 3px solid var(--petro-accent);
    border-radius: var(--petro-radius-md);
    background: linear-gradient(90deg, rgba(59,130,246,.09), rgba(59,130,246,.025));
    color: #a9b8cb;
    font-size: .78rem;
    font-weight: 560;
    line-height: 1.45;
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
    font-weight: 650;
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
    padding: .7rem .8rem;
    border: 1px solid var(--petro-border-strong);
    border-radius: var(--petro-radius-md);
    background: #111c2d;
    box-shadow: var(--petro-shadow-soft);
    color: var(--petro-text);
    font-size: .78rem;
    font-weight: 450;
    line-height: 1.5;
}
.petrolab-inline-help { margin: .08rem 0 .28rem; }
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
    gap: .75rem;
    margin: 1.05rem 0 .5rem;
    padding-bottom: .34rem;
    border-bottom: 1px solid var(--petro-border);
}
.petrolab-section-title-wrap {
    display: flex;
    align-items: center;
    gap: .4rem;
    min-width: 0;
}
.petrolab-section-title {
    font-weight: 700;
    font-size: .98rem;
    line-height: 1.3;
    letter-spacing: -.008em;
    margin: 0;
}
.petrolab-section-note {
    color: var(--petro-text-muted);
    font-size: .75rem;
    font-weight: 460;
}
.petrolab-reading-width { max-width: 920px; }

[data-testid="stMetric"] {
    border: 1px solid var(--petro-border);
    padding: .68rem .8rem;
    border-radius: var(--petro-radius-lg);
    background: linear-gradient(180deg, #111b2b, #0f1826);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.025);
}
[data-testid="stMetricLabel"] {
    color: var(--petro-text-muted);
    font-size: .72rem;
    font-weight: 620;
}
[data-testid="stMetricValue"] {
    color: var(--petro-text);
    letter-spacing: -.025em;
    font-weight: 730;
}

.petrolab-card,
[data-testid="stVerticalBlockBorderWrapper"] > div {
    border-color: var(--petro-border);
}
.petrolab-card {
    border: 1px solid var(--petro-border);
    border-radius: var(--petro-radius-lg);
    padding: .82rem .92rem;
    margin-bottom: .58rem;
    background: linear-gradient(180deg, #111a2a, #0f1826);
    box-shadow: inset 0 1px 0 rgba(255,255,255,.025);
}
.petrolab-card-soft {
    border: 1px solid var(--petro-border);
    border-radius: var(--petro-radius-lg);
    padding: .74rem .84rem;
    background: var(--petro-surface-soft);
}
.petrolab-card-active {
    border-color: var(--petro-accent-border);
    box-shadow: inset 3px 0 0 var(--petro-accent), 0 0 0 1px rgba(59,130,246,.06);
}
.petrolab-card-title { font-weight: 700; margin-bottom: .14rem; }
.petrolab-card-meta,
.petrolab-muted {
    color: var(--petro-text-muted);
    font-size: .78rem;
    line-height: 1.45;
}
.petrolab-big-number {
    font-size: 1.45rem;
    font-weight: 740;
    letter-spacing: -.025em;
    line-height: 1.05;
}

.petrolab-badges {
    display: flex;
    flex-wrap: wrap;
    gap: .32rem;
    margin: .24rem 0 .48rem;
}
.petrolab-badge {
    display: inline-flex;
    align-items: center;
    gap: .22rem;
    padding: .2rem .46rem;
    border-radius: 999px;
    font-size: .68rem;
    font-weight: 620;
    border: 1px solid var(--petro-border);
    background: rgba(255,255,255,.025);
    color: #aab8c9;
}
.petrolab-badge.accent { background: var(--petro-accent-soft); border-color: var(--petro-accent-border); color: #92c4ff; }
.petrolab-badge.success { background: var(--petro-success-soft); border-color: rgba(82,211,154,.25); color: var(--petro-success); }
.petrolab-badge.warning { background: var(--petro-warning-soft); border-color: rgba(242,189,87,.25); color: var(--petro-warning); }
.petrolab-badge.danger { background: var(--petro-danger-soft); border-color: rgba(255,127,135,.25); color: var(--petro-danger); }

.petrolab-toolbar {
    border: 1px solid var(--petro-border-strong);
    border-radius: var(--petro-radius-lg);
    background: #121d2e;
    padding: .55rem .62rem;
    margin: .25rem 0 .65rem;
    box-shadow: inset 0 1px 0 rgba(255,255,255,.025);
}
.petrolab-workspace {
    border: 1px solid var(--petro-border-strong);
    border-radius: var(--petro-radius-xl);
    background: #0f1826;
    padding: .72rem;
    box-shadow: var(--petro-shadow-soft);
}
.petrolab-export-zone {
    border-top: 1px solid var(--petro-border);
    margin-top: .78rem;
    padding-top: .68rem;
}
.petrolab-danger-zone {
    border: 1px solid rgba(255,127,135,.3);
    background: var(--petro-danger-soft);
    border-radius: var(--petro-radius-lg);
    padding: .68rem .78rem;
}

.petrolab-loading-card {
    max-width: 600px;
    margin: 8vh auto 0;
    padding: 1.25rem 1.35rem;
    border: 1px solid var(--petro-border-strong);
    border-radius: 14px;
    background: linear-gradient(180deg, #111b2b, #0d1624);
    box-shadow: 0 20px 55px rgba(0,0,0,.28);
}
.petrolab-loading-brand {
    display: flex;
    align-items: center;
    gap: .45rem;
    color: #dbeafe;
    font-weight: 740;
    font-size: .98rem;
    margin-bottom: .65rem;
}
.petrolab-loading-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--petro-accent);
    box-shadow: 0 0 0 5px rgba(59,130,246,.12);
}
.petrolab-loading-title { font-weight: 700; font-size: 1.03rem; margin-bottom: .22rem; }
.petrolab-loading-copy { color: var(--petro-text-muted); font-size: .8rem; line-height: 1.45; }
.petrolab-loading-line {
    height: 3px;
    margin-top: .9rem;
    border-radius: 999px;
    overflow: hidden;
    background: rgba(255,255,255,.055);
}
.petrolab-loading-line::after {
    content: "";
    display: block;
    width: 34%;
    height: 100%;
    border-radius: inherit;
    background: linear-gradient(90deg, transparent, #5aa2ff, transparent);
    animation: petrolab-load 1.15s ease-in-out infinite;
}
@keyframes petrolab-load {
    from { transform: translateX(-120%); }
    to { transform: translateX(360%); }
}

[data-testid="stSidebar"] {
    border-right: 1px solid #1f2d43;
    background: var(--petro-sidebar);
}
[data-testid="stSidebar"] > div:first-child { background: var(--petro-sidebar); }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .18rem; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { margin-bottom: 0; }
.petrolab-sidebar-brand {
    color: #f8fbff;
    font-size: 1.1rem;
    font-weight: 760;
    letter-spacing: -.02em;
    margin: .18rem 0 .01rem;
}
.petrolab-sidebar-version {
    color: #6f819a;
    font-size: .66rem;
    margin-bottom: .5rem;
}
.petrolab-nav-section {
    color: #71829a;
    font-size: .6rem;
    font-weight: 730;
    letter-spacing: .09em;
    text-transform: uppercase;
    margin: .62rem 0 .08rem;
}
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    min-height: 2.05rem;
    background: #111b2b !important;
    border-color: #26364e !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] svg { color: #dce7f5 !important; fill: #dce7f5 !important; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] {
    color: #71829a;
    font-size: .68rem;
    margin-top: -.04rem;
    margin-bottom: .28rem;
}
[data-testid="stSidebar"] .stButton > button {
    width: 100%;
    justify-content: flex-start;
    min-height: 2rem;
    padding: .3rem .55rem;
    border-radius: 8px;
    border: 1px solid transparent;
    background: transparent;
    color: #a8b6c8;
    box-shadow: none;
    font-weight: 570;
}
[data-testid="stSidebar"] .stButton > button p { color: inherit; }
[data-testid="stSidebar"] .stButton > button:hover {
    background: rgba(255,255,255,.045);
    color: #edf5ff;
    border-color: rgba(255,255,255,.03);
}
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
    background: rgba(59,130,246,.15) !important;
    color: #dceeff !important;
    border-color: rgba(96,165,250,.3) !important;
    box-shadow: inset 3px 0 0 var(--petro-accent) !important;
    font-weight: 680;
}
[data-testid="stSidebar"] .stButton > button[kind="primary"] p,
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] p { color: #dceeff !important; }
[data-testid="stSidebar"] [data-testid="stExpander"] {
    border: 0;
    background: transparent;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
    color: #8fa0b7;
    padding-left: .1rem;
}

[data-testid="stExpander"] {
    border-radius: var(--petro-radius-lg);
    border-color: var(--petro-border);
    background: #101927;
}
[data-testid="stExpander"] summary { font-weight: 620; color: #d9e3ef; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border-radius: 9px;
    overflow: hidden;
    border: 1px solid var(--petro-border-strong);
    background: #0d1623;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: .18rem;
    overflow-x: auto;
    border-bottom: 1px solid var(--petro-border);
    background: transparent;
    padding: 0 0 .15rem;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    white-space: nowrap;
    min-height: 2.15rem;
    padding: .28rem .65rem;
    border-radius: 8px 8px 0 0;
    color: #91a1b7;
    font-weight: 590;
}
[data-testid="stTabs"] [aria-selected="true"] {
    color: #eef6ff;
    background: rgba(59,130,246,.08);
    font-weight: 680;
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { height: 2px; background: var(--petro-accent); }

.stButton > button, .stDownloadButton > button {
    border-radius: 9px;
    min-height: 2.18rem;
    font-weight: 620;
    box-shadow: none;
    transition: background .16s ease, border-color .16s ease, transform .16s ease;
}
.stButton > button:not([kind="primary"]),
.stDownloadButton > button {
    background: #121d2d;
    color: #d5dfeb;
    border-color: #2a3a52;
}
.stButton > button:not([kind="primary"]):hover,
.stDownloadButton > button:hover {
    background: #18253a;
    color: #f4f8fd;
    border-color: #3a4d69;
}
.stButton > button[kind="primary"] {
    background: var(--petro-accent);
    border-color: var(--petro-accent);
    color: white;
}
.stButton > button[kind="primary"]:hover {
    background: var(--petro-accent-hover);
    border-color: var(--petro-accent-hover);
}

[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] > div,
textarea,
input {
    border-radius: 9px !important;
}
[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] > div {
    background: #101a29 !important;
    border-color: #2b3b54 !important;
}
[data-baseweb="input"] input,
[data-baseweb="textarea"] textarea { color: #edf5ff !important; }
[data-baseweb="input"] input::placeholder,
[data-baseweb="textarea"] textarea::placeholder { color: #64758d !important; }
[data-baseweb="select"] span,
[data-baseweb="select"] svg { color: #e4edf8 !important; fill: #e4edf8 !important; }

[data-testid="stFileUploaderDropzone"] {
    background: #0f1928;
    border: 1px dashed #365071;
    border-radius: 12px;
}
[data-testid="stCaptionContainer"] {
    color: var(--petro-text-muted);
    font-size: .73rem;
    line-height: 1.4;
}
[data-testid="stAlert"] {
    border-radius: 10px;
    padding-top: .48rem;
    padding-bottom: .48rem;
    border: 1px solid var(--petro-border);
}
hr { border-color: var(--petro-border) !important; }

button:focus-visible,
input:focus-visible,
textarea:focus-visible,
[role="combobox"]:focus-visible,
[role="radio"]:focus-visible {
    outline: 2px solid #62a7ff !important;
    outline-offset: 2px !important;
}

@media (max-width: 1100px) {
    .block-container { padding-left: .82rem; padding-right: .82rem; }
    [data-testid="column"] { min-width: 0 !important; }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap: .12rem; }
    .petrolab-nav-section { margin-top: .48rem; }
}
@media (max-width: 760px) {
    .block-container { padding-left: .58rem; padding-right: .58rem; padding-top: .65rem; }
    h1, .petrolab-page-title { font-size: 1.46rem; }
    h2 { font-size: 1.05rem; }
    .petrolab-section-header { align-items: flex-start; margin: .85rem 0 .4rem; }
    .petrolab-section-title { font-size: .96rem; }
    .petrolab-section-note { font-size: .72rem; line-height: 1.35; }
    .petrolab-workspace { padding: .52rem; border-radius: var(--petro-radius-md); }
    .petrolab-card { padding: .66rem .7rem; }
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
            .block-container { max-width: 1760px; }
            [data-testid="stVerticalBlock"] { gap: .38rem; }
            [data-testid="stMetric"] { padding: .56rem .66rem; }
            .petrolab-card { padding: .64rem .72rem; margin-bottom: .42rem; }
            .petrolab-page-header { margin-bottom: .72rem; }
            </style>
            """,
            unsafe_allow_html=True,
        )
