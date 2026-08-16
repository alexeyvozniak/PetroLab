from __future__ import annotations

import streamlit as st


_CSS = r"""
<style>
/*
Acceptance hardening for the widths where a persistent sidebar leaves a narrow
scientific work area. The rules are deliberately structural rather than tied to
arbitrary page text: Chrome/Edge/Firefox/Safari all support :has() in current
versions. Mobile keeps the existing Streamlit stack behavior.
*/

/* Home: do not squeeze seven quick actions into unreadable buttons on laptops. */
@media (min-width: 768px) and (max-width: 1150px) {
  [data-testid="stHorizontalBlock"]:has(.st-key-home_workspace) {
    flex-wrap: wrap !important;
  }
  [data-testid="stHorizontalBlock"]:has(.st-key-home_workspace) > [data-testid="stColumn"] {
    flex: 1 1 145px !important;
    width: auto !important;
    min-width: 145px !important;
  }

  /* Canonical analysis table: search gets a full row; view controls get useful width. */
  [data-testid="stHorizontalBlock"]:has(input[placeholder*="Sample, Grain, Point"]) {
    flex-wrap: wrap !important;
  }
  [data-testid="stHorizontalBlock"]:has(input[placeholder*="Sample, Grain, Point"]) > [data-testid="stColumn"]:first-child {
    flex: 1 1 100% !important;
    width: 100% !important;
    min-width: 100% !important;
  }
  [data-testid="stHorizontalBlock"]:has(input[placeholder*="Sample, Grain, Point"]) > [data-testid="stColumn"]:not(:first-child) {
    flex: 1 1 110px !important;
    width: auto !important;
    min-width: 110px !important;
  }

  /* XY workbench: the scientific result comes before the configuration panel. */
  [data-testid="stHorizontalBlock"]:has([data-testid="stPlotlyChart"]) {
    flex-direction: column !important;
  }
  [data-testid="stHorizontalBlock"]:has([data-testid="stPlotlyChart"]) > [data-testid="stColumn"] {
    flex: 1 1 100% !important;
    width: 100% !important;
    min-width: 0 !important;
  }
  [data-testid="stHorizontalBlock"]:has([data-testid="stPlotlyChart"]) > [data-testid="stColumn"]:has([data-testid="stPlotlyChart"]) {
    order: 1 !important;
  }
  [data-testid="stHorizontalBlock"]:has([data-testid="stPlotlyChart"]) > [data-testid="stColumn"]:not(:has([data-testid="stPlotlyChart"])) {
    order: 2 !important;
  }
}

/* Wide desktop: still give the plot more of the workbench than the control rail. */
@media (min-width: 1151px) {
  [data-testid="stHorizontalBlock"]:has([data-testid="stPlotlyChart"]) > [data-testid="stColumn"]:first-child {
    flex: 0.85 1 0 !important;
    width: 0 !important;
    min-width: 0 !important;
  }
  [data-testid="stHorizontalBlock"]:has([data-testid="stPlotlyChart"]) > [data-testid="stColumn"]:has([data-testid="stPlotlyChart"]) {
    flex: 2.35 1 0 !important;
    width: 0 !important;
    min-width: 0 !important;
  }
}
</style>
"""


def apply_acceptance_layout() -> None:
    """Apply responsive layout guards proven by the real-browser acceptance suite."""
    st.markdown(_CSS, unsafe_allow_html=True)
