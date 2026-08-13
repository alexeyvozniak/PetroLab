from __future__ import annotations

import streamlit as st


CSS = r"""
<style>
:root {
    --petro-radius: 14px;
    --petro-border: rgba(120,120,120,.20);
    --petro-muted: rgba(120,120,120,.09);
}
.block-container {
    padding-top: 1.15rem;
    padding-bottom: 4rem;
    max-width: 1540px;
}
h1, h2, h3 { letter-spacing: -0.025em; }
h1 { margin-bottom: .6rem; }
[data-testid="stMetric"] {
    border: 1px solid var(--petro-border);
    padding: .8rem 1rem;
    border-radius: var(--petro-radius);
    background: rgba(127,127,127,.025);
}
[data-testid="stExpander"] {
    border-radius: var(--petro-radius);
}
[data-testid="stDataFrame"] {
    border-radius: 12px;
    overflow: hidden;
}
.stButton > button, .stDownloadButton > button {
    border-radius: 10px;
    min-height: 2.45rem;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: .15rem;
    overflow-x: auto;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    white-space: nowrap;
}
.petrolab-card {
    border: 1px solid var(--petro-border);
    border-radius: var(--petro-radius);
    padding: 1rem 1.1rem;
    margin-bottom: .8rem;
    background: rgba(127,127,127,.025);
}
.petrolab-muted { opacity: .72; font-size: .9rem; }
.petrolab-step {
    border-left: 3px solid rgba(90,110,130,.55);
    padding-left: .85rem;
    margin: .6rem 0 1rem;
}
@media (max-width: 900px) {
    .block-container { padding-left: .8rem; padding-right: .8rem; padding-top: .7rem; }
    [data-testid="column"] { min-width: 0 !important; }
    h1 { font-size: 1.75rem; }
    h2 { font-size: 1.35rem; }
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
            [data-testid="stVerticalBlock"] { gap: .65rem; }
            [data-testid="stMetric"] { padding: .55rem .75rem; }
            </style>
            """,
            unsafe_allow_html=True,
        )
