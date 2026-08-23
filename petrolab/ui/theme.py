from __future__ import annotations

import streamlit as st


CSS = r"""
<style>
:root {
    --petro-bg: #f6f8fa;
    --petro-surface: #ffffff;
    --petro-surface-soft: #f8fafb;
    --petro-surface-strong: #eef3f5;
    --petro-sidebar: #10283a;
    --petro-sidebar-hover: #17394f;
    --petro-text: #162033;
    --petro-text-muted: #68758a;
    --petro-border: #dce3e8;
    --petro-border-strong: #cbd6dd;
    --petro-accent: #0f7f82;
    --petro-accent-hover: #0b696c;
    --petro-accent-soft: #e7f5f4;
    --petro-success: #238750;
    --petro-success-soft: #edf8f1;
    --petro-warning: #a76b13;
    --petro-warning-soft: #fff7e8;
    --petro-danger: #b94a55;
    --petro-danger-soft: #fff0f1;
    --petro-radius-sm: 6px;
    --petro-radius-md: 8px;
    --petro-radius-lg: 10px;
    --petro-shadow-soft: 0 1px 2px rgba(22,32,51,.05);
}

html, body, [class*="css"], [data-testid="stAppViewContainer"] {
    font-family: "Segoe UI", Inter, Arial, sans-serif;
    color: var(--petro-text);
}
body { font-weight: 450; }
[data-testid="stAppViewContainer"] { background: var(--petro-bg); }
[data-testid="stHeader"] {
    background: rgba(246,248,250,.96);
    border-bottom: 1px solid var(--petro-border);
}
.block-container {
    padding-top: .9rem;
    padding-bottom: 2.4rem;
    max-width: 1760px;
}

h1, h2, h3 {
    font-family: "Segoe UI", Inter, Arial, sans-serif;
    color: var(--petro-text);
    letter-spacing: -.02em;
}
h1 { font-size: clamp(1.55rem, 1.9vw, 1.92rem); font-weight: 740; line-height: 1.16; }
h2 { font-size: 1.06rem; font-weight: 700; }
h3 { font-size: .95rem; font-weight: 690; }

.petrolab-page-header {
    margin: 0 0 .72rem;
    padding: .05rem 0 .58rem;
    border-bottom: 1px solid var(--petro-border);
}
.petrolab-eyebrow {
    color: var(--petro-accent);
    font-size: .62rem;
    font-weight: 740;
    letter-spacing: .08em;
    text-transform: uppercase;
    margin-bottom: .12rem;
}
.petrolab-page-title-row { display:flex; align-items:center; gap:.42rem; }
.petrolab-page-title {
    font-size: clamp(1.55rem, 1.9vw, 1.92rem);
    line-height: 1.16;
    font-weight: 740;
    margin: 0;
}
.petrolab-context-line { color: var(--petro-text-muted); font-size:.74rem; margin-top:.22rem; }
.petrolab-section-header {
    display:flex; align-items:center; justify-content:space-between;
    margin:.84rem 0 .38rem; padding-bottom:.24rem;
    border-bottom:1px solid var(--petro-border);
}
.petrolab-section-title-wrap { display:flex; align-items:center; gap:.34rem; }
.petrolab-section-title { font-size:.94rem; font-weight:700; margin:0; }
.petrolab-work-context {
    margin:.34rem 0 .56rem; padding:.48rem .62rem;
    border:1px solid var(--petro-border); border-left:3px solid var(--petro-accent);
    border-radius:var(--petro-radius-sm); background:var(--petro-surface-soft);
    color:var(--petro-text-muted); font-size:.75rem;
}
.petrolab-page-help > summary,
.petrolab-inline-help > summary,
.petrolab-section-help > summary { color:var(--petro-text-muted); cursor:pointer; list-style:none; }
.petrolab-page-help > summary::-webkit-details-marker,
.petrolab-inline-help > summary::-webkit-details-marker,
.petrolab-section-help > summary::-webkit-details-marker { display:none; }
.petrolab-page-help[open] > div,
.petrolab-inline-help[open] > div,
.petrolab-section-help[open] > div {
    position:absolute; z-index:1000; width:min(32rem,70vw); padding:.62rem .7rem;
    border:1px solid var(--petro-border-strong); border-radius:8px; background:white;
    box-shadow:0 10px 30px rgba(22,32,51,.12); color:var(--petro-text); font-size:.76rem;
}
.petrolab-inline-help { position:relative; display:inline-block; }
.petrolab-inline-help[open] > div { position:relative; width:min(52rem,100%); box-shadow:none; background:var(--petro-surface-soft); }

.petrolab-card, .petrolab-card-soft, .petrolab-workspace, .petrolab-toolbar {
    border:1px solid var(--petro-border);
    background:var(--petro-surface);
    border-radius:var(--petro-radius-md);
    box-shadow:var(--petro-shadow-soft);
}
.petrolab-card { padding:.72rem .8rem; margin-bottom:.5rem; }
.petrolab-card-soft { padding:.64rem .72rem; background:var(--petro-surface-soft); }
.petrolab-card-active { border-color:#8dc4c6; box-shadow:inset 3px 0 0 var(--petro-accent); }
.petrolab-card-title { font-weight:690; margin-bottom:.12rem; }
.petrolab-card-meta, .petrolab-muted { color:var(--petro-text-muted); font-size:.76rem; line-height:1.4; }
.petrolab-toolbar { padding:.45rem .52rem; margin:.18rem 0 .52rem; }
.petrolab-workspace { padding:.58rem; }
.petrolab-danger-zone { border:1px solid #e7c2c6; background:var(--petro-danger-soft); border-radius:8px; padding:.6rem .68rem; }

.petrolab-badges { display:flex; flex-wrap:wrap; gap:.28rem; margin:.16rem 0 .38rem; }
.petrolab-badge {
    display:inline-flex; align-items:center; padding:.16rem .38rem; border-radius:999px;
    border:1px solid var(--petro-border); background:#fff; color:var(--petro-text-muted);
    font-size:.67rem; font-weight:620;
}
.petrolab-badge.accent { background:var(--petro-accent-soft); border-color:#b7dad8; color:var(--petro-accent-hover); }
.petrolab-badge.success { background:var(--petro-success-soft); border-color:#c7e6d2; color:var(--petro-success); }
.petrolab-badge.warning { background:var(--petro-warning-soft); border-color:#efd7aa; color:var(--petro-warning); }
.petrolab-badge.danger { background:var(--petro-danger-soft); border-color:#e7c2c6; color:var(--petro-danger); }

/* Reference-style static shells */
.pd-screen-title { font-size:1.15rem; font-weight:720; color:var(--petro-text); margin-bottom:.12rem; }
.pd-screen-subtitle { color:var(--petro-text-muted); font-size:.75rem; }
.pd-status-strip {
    display:flex; flex-wrap:wrap; gap:1.2rem; align-items:center;
    border:1px solid var(--petro-border); background:#fff; border-radius:8px;
    padding:.62rem .72rem; margin:.2rem 0 .65rem;
}
.pd-status-item { min-width:8.5rem; }
.pd-status-item strong { display:block; font-size:.72rem; color:var(--petro-text); }
.pd-status-item span { display:block; font-size:.66rem; color:var(--petro-text-muted); margin-top:.05rem; }
.pd-panel-title { font-size:.82rem; font-weight:700; color:var(--petro-text); margin-bottom:.18rem; }
.pd-big-count { font-size:1.48rem; font-weight:730; letter-spacing:-.03em; line-height:1; }
.pd-chip {
    display:inline-flex; gap:.28rem; align-items:center; margin:.12rem .14rem .12rem 0;
    padding:.22rem .42rem; border:1px solid var(--petro-border); border-radius:6px;
    background:#fff; color:#46566c; font-size:.69rem;
}
.pd-dot { width:.5rem; height:.5rem; border-radius:50%; display:inline-block; background:var(--petro-accent); }
.pd-note-card { border:1px solid #cfe0e5; background:#f7fbfc; border-radius:8px; padding:.6rem .7rem; font-size:.72rem; color:#5d6e82; }
.pd-warning-card { border:1px solid #efd7aa; background:var(--petro-warning-soft); border-radius:8px; padding:.6rem .7rem; font-size:.72rem; color:#77521c; }

[data-testid="stMetric"] {
    border:1px solid var(--petro-border); padding:.58rem .7rem; border-radius:8px;
    background:#fff; box-shadow:none;
}
[data-testid="stMetricLabel"] { color:var(--petro-text-muted); font-size:.72rem; font-weight:600; }
[data-testid="stMetricValue"] { color:var(--petro-text); font-weight:700; }

/* Sidebar: narrow dark scientific rail from the references. */
[data-testid="stSidebar"] { border-right:1px solid #153449; background:var(--petro-sidebar); }
[data-testid="stSidebar"] > div:first-child { background:var(--petro-sidebar); }
[data-testid="stSidebar"] [data-testid="stVerticalBlock"] { gap:.12rem; }
.petrolab-sidebar-brand { color:#22c1bf; font-size:1.08rem; font-weight:740; margin:.14rem 0 .02rem; }
.petrolab-sidebar-version { color:#6f8a9d; font-size:.64rem; margin-bottom:.38rem; }
.petrolab-nav-section { color:#6f899b; font-size:.58rem; font-weight:720; letter-spacing:.08em; text-transform:uppercase; margin:.46rem 0 .06rem; }
[data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color:#7e96a8; font-size:.65rem; }
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    min-height:1.96rem; background:#0d2232 !important; border-color:#24485e !important; border-radius:6px !important;
}
[data-testid="stSidebar"] [data-baseweb="select"] span,
[data-testid="stSidebar"] [data-baseweb="select"] svg { color:#d9e7ef !important; fill:#d9e7ef !important; }
[data-testid="stSidebar"] .stButton > button {
    width:100%; justify-content:flex-start; min-height:1.9rem; padding:.26rem .42rem;
    border-radius:6px; border:1px solid transparent; background:transparent; color:#d3e0e7;
    box-shadow:none; font-weight:560;
}
[data-testid="stSidebar"] .stButton > button p { color:inherit; }
[data-testid="stSidebar"] .stButton > button:hover { background:var(--petro-sidebar-hover); border-color:transparent; }
[data-testid="stSidebar"] .stButton > button[kind="primary"],
[data-testid="stSidebar"] [data-testid="stBaseButton-primary"] {
    background:#173b50 !important; color:#f3fbff !important; border-color:#24566f !important;
    border-left:3px solid #18b6b2 !important; font-weight:650;
}
[data-testid="stSidebar"] [data-testid="stExpander"] { border:0; background:transparent; }
[data-testid="stSidebar"] [data-testid="stExpander"] summary { color:#9db0bd; }

[data-testid="stExpander"] { border:1px solid var(--petro-border); border-radius:8px; background:#fff; }
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border:1px solid var(--petro-border-strong); border-radius:6px; overflow:hidden; background:#fff;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap:.28rem; overflow-x:auto; border-bottom:1px solid var(--petro-border); background:transparent; padding:0;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    min-height:2.18rem; padding:.25rem .54rem; white-space:nowrap; color:#607086; font-weight:590;
}
[data-testid="stTabs"] [aria-selected="true"] { color:var(--petro-accent-hover); font-weight:690; }
[data-testid="stTabs"] [data-baseweb="tab-highlight"] { height:2px; background:var(--petro-accent); }

.stButton > button, .stDownloadButton > button {
    border-radius:6px; min-height:2.08rem; font-weight:620; box-shadow:none;
}
.stButton > button:not([kind="primary"]), .stDownloadButton > button {
    background:#fff; color:#32435a; border-color:var(--petro-border-strong);
}
.stButton > button:not([kind="primary"]):hover, .stDownloadButton > button:hover {
    background:#f5f9fa; border-color:#a9c4c9; color:#17384a;
}
.stButton > button[kind="primary"] { background:var(--petro-accent); border-color:var(--petro-accent); color:#fff; }
.stButton > button[kind="primary"]:hover { background:var(--petro-accent-hover); border-color:var(--petro-accent-hover); }

[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] > div,
textarea, input { border-radius:6px !important; }
[data-baseweb="input"] > div,
[data-baseweb="select"] > div,
[data-baseweb="textarea"] > div { background:#fff !important; border-color:var(--petro-border-strong) !important; }
[data-testid="stFileUploaderDropzone"] {
    min-height:7rem; background:#fbfcfd; border:1px dashed #b8c7d2; border-radius:8px;
}
[data-testid="stCaptionContainer"] { color:var(--petro-text-muted); font-size:.71rem; line-height:1.35; }
[data-testid="stAlert"] { border-radius:7px; border:1px solid var(--petro-border); }

.petrolab-loading-card {
    max-width:560px; margin:8vh auto 0; padding:1.1rem 1.2rem;
    border:1px solid var(--petro-border); border-radius:10px; background:#fff; box-shadow:0 12px 34px rgba(22,32,51,.08);
}
.petrolab-loading-brand { color:var(--petro-accent); font-weight:720; margin-bottom:.45rem; }
.petrolab-loading-title { font-weight:680; font-size:1rem; margin-bottom:.18rem; }
.petrolab-loading-copy { color:var(--petro-text-muted); font-size:.78rem; }
.petrolab-loading-line { height:3px; margin-top:.75rem; border-radius:999px; overflow:hidden; background:#edf2f4; }
.petrolab-loading-line::after {
    content:""; display:block; width:34%; height:100%; border-radius:inherit; background:var(--petro-accent);
    animation:petrolab-load 1.1s ease-in-out infinite;
}
@keyframes petrolab-load { from { transform:translateX(-120%); } to { transform:translateX(360%); } }

button:focus-visible, input:focus-visible, textarea:focus-visible, [role="combobox"]:focus-visible {
    outline:2px solid #57aeb1 !important; outline-offset:2px !important;
}

@media (max-width:1100px) {
    .block-container { padding-left:.72rem; padding-right:.72rem; }
    [data-testid="column"] { min-width:0 !important; }
}
@media (max-width:760px) {
    .block-container { padding-left:.52rem; padding-right:.52rem; padding-top:.58rem; }
    h1, .petrolab-page-title { font-size:1.36rem; }
    .stButton > button, .stDownloadButton > button { min-height:2.4rem; }
}
</style>
"""


def apply_theme(ui_density: str = "comfortable") -> None:
    st.markdown(CSS, unsafe_allow_html=True)
    if ui_density == "compact":
        st.markdown(
            """
            <style>
            [data-testid="stVerticalBlock"] { gap:.38rem; }
            [data-testid="stMetric"] { padding:.48rem .6rem; }
            .petrolab-card { padding:.58rem .66rem; margin-bottom:.4rem; }
            .petrolab-page-header { margin-bottom:.58rem; }
            </style>
            """,
            unsafe_allow_html=True,
        )
