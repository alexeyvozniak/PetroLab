from __future__ import annotations

import streamlit as st


CSS = r"""
<style>
:root {
    --petro-bg: #ffffff;
    --petro-surface: #ffffff;
    --petro-surface-soft: #f7f9fa;
    --petro-surface-strong: #eef3f4;
    --petro-sidebar: #ffffff;
    --petro-sidebar-hover: #f3f7f7;
    --petro-text: #172230;
    --petro-text-muted: #6c7886;
    --petro-border: #dfe5e8;
    --petro-border-strong: #cfd8dd;
    --petro-accent: #0b7f7a;
    --petro-accent-hover: #086963;
    --petro-accent-soft: #e8f5f3;
    --petro-success: #238750;
    --petro-success-soft: #edf8f1;
    --petro-warning: #9b6817;
    --petro-warning-soft: #fff7e8;
    --petro-danger: #b94a55;
    --petro-danger-soft: #fff0f1;
    --petro-radius-sm: 5px;
    --petro-radius-md: 7px;
    --petro-radius-lg: 9px;
    --petro-shadow-soft: 0 1px 2px rgba(25,35,45,.035);
}

html, body, [class*="css"], [data-testid="stAppViewContainer"] {
    font-family: "Segoe UI", Inter, Arial, sans-serif;
    color: var(--petro-text);
}
body { font-weight: 450; }
[data-testid="stAppViewContainer"] { background: var(--petro-bg); }
[data-testid="stHeader"] {
    background: rgba(255,255,255,.97);
    border-bottom: 1px solid var(--petro-border);
}
[data-testid="stToolbar"] { color: var(--petro-text-muted); }
.block-container {
    padding-top: .72rem;
    padding-bottom: 2.5rem;
    max-width: 1780px;
}

h1, h2, h3 {
    font-family: "Segoe UI", Inter, Arial, sans-serif;
    color: var(--petro-text);
    letter-spacing: -.018em;
}
h1 { font-size: clamp(1.48rem, 1.8vw, 1.82rem); font-weight: 730; line-height: 1.16; }
h2 { font-size: 1.02rem; font-weight: 700; }
h3 { font-size: .92rem; font-weight: 690; }

.petrolab-page-header {
    margin: 0 0 .62rem;
    padding: .02rem 0 .48rem;
    border-bottom: 1px solid var(--petro-border);
}
.petrolab-eyebrow {
    color: var(--petro-accent);
    font-size: .6rem;
    font-weight: 740;
    letter-spacing: .07em;
    text-transform: uppercase;
    margin-bottom: .08rem;
}
.petrolab-page-title-row { display:flex; align-items:center; gap:.38rem; }
.petrolab-page-title {
    font-size: clamp(1.48rem, 1.8vw, 1.82rem);
    line-height: 1.16;
    font-weight: 730;
    margin: 0;
}
.petrolab-page-lead,
.petrolab-context-line { color: var(--petro-text-muted); font-size:.72rem; margin-top:.18rem; line-height:1.42; }
.petrolab-section-header {
    display:flex; align-items:center; justify-content:space-between;
    margin:.76rem 0 .32rem; padding-bottom:.2rem;
    border-bottom:1px solid var(--petro-border);
}
.petrolab-section-title-wrap { display:flex; align-items:center; gap:.32rem; }
.petrolab-section-title { font-size:.9rem; font-weight:700; margin:0; }
.petrolab-section-note { color:var(--petro-text-muted); font-size:.7rem; }
.petrolab-work-context {
    margin:.28rem 0 .48rem; padding:.4rem .56rem;
    border:1px solid var(--petro-border); border-left:3px solid var(--petro-accent);
    border-radius:var(--petro-radius-sm); background:#fbfcfc;
    color:var(--petro-text-muted); font-size:.72rem;
}
.petrolab-reading-width { max-width: 920px; }

.petrolab-page-help, .petrolab-inline-help, .petrolab-section-help { position:relative; display:inline-block; }
.petrolab-page-help > summary,
.petrolab-inline-help > summary,
.petrolab-section-help > summary { color:var(--petro-text-muted); cursor:pointer; list-style:none; font-size:.72rem; }
.petrolab-page-help > summary::-webkit-details-marker,
.petrolab-inline-help > summary::-webkit-details-marker,
.petrolab-section-help > summary::-webkit-details-marker { display:none; }
.petrolab-page-help[open] > div,
.petrolab-inline-help[open] > div,
.petrolab-section-help[open] > div {
    position:absolute; z-index:1000; width:min(32rem,70vw); padding:.56rem .64rem;
    border:1px solid var(--petro-border-strong); border-radius:7px; background:white;
    box-shadow:0 10px 28px rgba(22,32,51,.11); color:var(--petro-text); font-size:.74rem;
}
.petrolab-inline-help[open] > div { position:relative; width:min(52rem,100%); box-shadow:none; background:var(--petro-surface-soft); }

.petrolab-card, .petrolab-card-soft, .petrolab-workspace, .petrolab-toolbar {
    border:1px solid var(--petro-border);
    background:var(--petro-surface);
    border-radius:var(--petro-radius-md);
    box-shadow:var(--petro-shadow-soft);
}
.petrolab-card { padding:.64rem .72rem; margin-bottom:.42rem; }
.petrolab-card-soft { padding:.58rem .66rem; background:var(--petro-surface-soft); }
.petrolab-card-active { border-color:#8dc4c6; box-shadow:inset 3px 0 0 var(--petro-accent); }
.petrolab-card-title { font-weight:690; margin-bottom:.1rem; }
.petrolab-card-meta, .petrolab-muted { color:var(--petro-text-muted); font-size:.72rem; line-height:1.4; }
.petrolab-big-number { font-size:1.34rem; font-weight:720; letter-spacing:-.025em; }
.petrolab-toolbar { padding:.38rem .46rem; margin:.14rem 0 .46rem; }
.petrolab-workspace { padding:.5rem; }
.petrolab-export-zone { border-top:1px solid var(--petro-border); margin-top:.64rem; padding-top:.56rem; }
.petrolab-danger-zone { border:1px solid #e7c2c6; background:var(--petro-danger-soft); border-radius:7px; padding:.54rem .62rem; }

.petrolab-badges { display:flex; flex-wrap:wrap; gap:.24rem; margin:.14rem 0 .32rem; }
.petrolab-badge {
    display:inline-flex; align-items:center; padding:.14rem .34rem; border-radius:999px;
    border:1px solid var(--petro-border); background:#fff; color:var(--petro-text-muted);
    font-size:.64rem; font-weight:620;
}
.petrolab-badge.accent { background:var(--petro-accent-soft); border-color:#b7dad8; color:var(--petro-accent-hover); }
.petrolab-badge.success { background:var(--petro-success-soft); border-color:#c7e6d2; color:var(--petro-success); }
.petrolab-badge.warning { background:var(--petro-warning-soft); border-color:#efd7aa; color:var(--petro-warning); }
.petrolab-badge.danger { background:var(--petro-danger-soft); border-color:#e7c2c6; color:var(--petro-danger); }

/* Reference-system primitives used by the screenshot-led pages. */
.pd-screen-title { font-size:1.12rem; font-weight:720; color:var(--petro-text); margin-bottom:.1rem; }
.pd-screen-subtitle { color:var(--petro-text-muted); font-size:.71rem; }
.pd-status-strip {
    display:flex; flex-wrap:wrap; gap:1rem; align-items:center;
    border:1px solid var(--petro-border); background:#fff; border-radius:7px;
    padding:.5rem .62rem; margin:.16rem 0 .54rem;
}
.pd-status-item { min-width:8rem; }
.pd-status-item strong { display:block; font-size:.7rem; color:var(--petro-text); }
.pd-status-item span { display:block; font-size:.63rem; color:var(--petro-text-muted); margin-top:.04rem; }
.pd-panel-title { font-size:.8rem; font-weight:700; color:var(--petro-text); margin-bottom:.16rem; }
.pd-big-count { font-size:1.38rem; font-weight:730; letter-spacing:-.03em; line-height:1; }
.pd-chip {
    display:inline-flex; gap:.24rem; align-items:center; margin:.1rem .12rem .1rem 0;
    padding:.18rem .36rem; border:1px solid var(--petro-border); border-radius:5px;
    background:#fff; color:#46566c; font-size:.65rem;
}
.pd-dot { width:.44rem; height:.44rem; border-radius:50%; display:inline-block; background:var(--petro-accent); }
.pd-note-card { border:1px solid #cfe0e5; background:#f8fbfb; border-radius:7px; padding:.54rem .62rem; font-size:.7rem; color:#5d6e82; }
.pd-warning-card { border:1px solid #efd7aa; background:var(--petro-warning-soft); border-radius:7px; padding:.54rem .62rem; font-size:.7rem; color:#77521c; }

/* Bottom Selection tray from the approved reference. */
.petrolab-selection-tray {
    position:sticky; bottom:.35rem; z-index:50;
    border:1px solid #a9cfd0; background:rgba(255,255,255,.97);
    border-radius:7px; box-shadow:0 7px 22px rgba(24,47,57,.08);
    padding:.42rem .5rem; margin-top:.45rem;
    backdrop-filter: blur(8px);
}

[data-testid="stMetric"] {
    border:1px solid var(--petro-border); padding:.5rem .62rem; border-radius:7px;
    background:#fff; box-shadow:none;
}
[data-testid="stMetricLabel"] { color:var(--petro-text-muted); font-size:.68rem; font-weight:600; }
[data-testid="stMetricValue"] { color:var(--petro-text); font-weight:700; font-size:1.15rem; }

/* Global light navigation rail. */
[data-testid="stSidebar"] { border-right:1px solid var(--petro-border); background:#fff; }
[data-testid="stSidebar"] > div:first-child { background:#fff; }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap:.1rem; }
.petrolab-sidebar-brand { color:var(--petro-accent); font-size:1.02rem; font-weight:740; margin:.12rem 0 .01rem; }
.petrolab-sidebar-version { color:#87929d; font-size:.61rem; margin-bottom:.32rem; }
.petrolab-nav-section { color:#8a96a1; font-size:.56rem; font-weight:720; letter-spacing:.07em; text-transform:uppercase; margin:.4rem 0 .04rem; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color:#7f8b96; font-size:.63rem; }
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    min-height:1.88rem; background:#fff !important; border-color:#d5dde3 !important; border-radius:5px !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] svg { color:#334155 !important; fill:#334155 !important; }
[data-testid="stSidebar"] .stButton > button {
    width:100%; justify-content:flex-start; min-height:1.82rem; padding:.22rem .38rem;
    border-radius:5px; border:1px solid transparent; background:transparent; color:#4b5969;
    box-shadow:none; font-weight:560;
}
[data-testid="stSidebar"] .stButton > button p { color:inherit; }
[data-testid="stSidebar"] .stButton > button:hover { background:#f3f7f7; color:#24434b; border-color:transparent; }
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
    background:var(--petro-accent-soft) !important; color:#0a6c68 !important;
    border-color:#c3dfdd !important; border-left:3px solid var(--petro-accent) !important; font-weight:650;
}
[data-testid="stSidebar"] [data-testid="stExpander"] { border:0; background:transparent; }
[data-testid="stSidebar"] [data-testid="stExpander"] summary { color:#71808f; }

[data-testid="stExpander"] { border:1px solid var(--petro-border); border-radius:7px; background:#fff; }
[data-testid="stExpander"] summary { font-weight:620; color:#38495b; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border:1px solid var(--petro-border-strong); border-radius:5px; overflow:hidden; background:#fff;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap:.24rem; overflow-x:auto; border-bottom:1px solid var(--petro-border); background:transparent; padding:0;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    min-height:2rem; padding:.22rem .48rem; white-space:nowrap; color:#607086; font-weight:590; font-size:.76rem;
}
[data-testid="stTabs"] [aria-selected="true"] { color:var(--petro-accent-hover); font-weight:690; }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { height:2px; background:var(--petro-accent); }

.stButton > button, .stDownloadButton > button {
    border-radius:5px; min-height:1.98rem; font-weight:620; box-shadow:none; font-size:.75rem;
}
.stButton > button:not([kind="primary"]), .stDownloadButton > button {
    background:#fff; color:#32435a; border-color:var(--petro-border-strong);
}
.stButton > button:not([kind="primary"]):hover, .stDownloadButton > button:hover {
    background:#f5f9f9; border-color:#a9c4c9; color:#17384a;
}
.stButton > button[kind="primary"] { background:var(--petro-accent); border-color:var(--petro-accent); color:#fff; }
.stButton > button[kind="primary"]:hover { background:var(--petro-accent-hover); border-color:var(--petro-accent-hover); }

[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] > div,
textarea, input { border-radius:5px !important; }
[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] > div { background:#fff !important; border-color:var(--petro-border-strong) !important; }
[data-testid="stFileUploaderDropzone"] {
    min-height:6.5rem; background:#fbfcfc; border:1px dashed #b8c7d2; border-radius:7px;
}
[data-testid="stCaptionContainer"] { color:var(--petro-text-muted); font-size:.68rem; line-height:1.34; }
[data-testid="stAlert"] { border-radius:6px; border:1px solid var(--petro-border); padding-top:.44rem; padding-bottom:.44rem; }
hr { border-color:var(--petro-border) !important; }

.petrolab-loading-card {
    max-width:540px; margin:8vh auto 0; padding:1rem 1.1rem;
    border:1px solid var(--petro-border); border-radius:9px; background:#fff; box-shadow:0 12px 32px rgba(22,32,51,.07);
}
.petrolab-loading-brand { color:var(--petro-accent); font-weight:720; margin-bottom:.4rem; }
.petrolab-loading-title { font-weight:680; font-size:.96rem; margin-bottom:.16rem; }
.petrolab-loading-copy { color:var(--petro-text-muted); font-size:.74rem; }
.petrolab-loading-line { height:3px; margin-top:.68rem; border-radius:999px; overflow:hidden; background:#edf2f4; }
.petrolab-loading-line::after {
    content:""; display:block; width:34%; height:100%; border-radius:inherit; background:var(--petro-accent);
    animation:petrolab-load 1.1s ease-in-out infinite;
}
@keyframes petrolab-load { from { transform:translateX(-120%); } to { transform:translateX(360%); } }

button:focus-visible, input:focus-visible, textarea:focus-visible, [role="combobox"]:focus-visible, [role="checkbox"]:focus-visible {
    outline:2px solid #57aeb1 !important; outline-offset:2px !important;
}

@media (max-width:1100px) {
    .block-container { padding-left:.68rem; padding-right:.68rem; }
    [data-testid="column"] { min-width:0 !important; }
}
@media (max-width:760px) {
    .block-container { padding-left:.48rem; padding-right:.48rem; padding-top:.5rem; }
    h1, .petrolab-page-title { font-size:1.3rem; }
    .stButton > button, .stDownloadButton > button { min-height:2.3rem; }
    .petrolab-selection-tray { position:relative; bottom:auto; }
}
</style>
"""


def apply_theme(ui_density: str = "comfortable") -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if ui_density == "compact":
        st.markdown(
            """
            <style>
            [data-testid="stVerticalBlock"] { gap:.32rem; }
            [data-testid="stMetric"] { padding:.42rem .54rem; }
            .petrolab-card { padding:.52rem .6rem; margin-bottom:.34rem; }
            .petrolab-page-header { margin-bottom:.5rem; }
            </style>
            """,
            unsafe_allow_html=True,
        )
