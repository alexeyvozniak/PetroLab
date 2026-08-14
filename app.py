from __future__ import annotations

import hashlib
import json

import streamlit as st

from petrolab import __version__
from petrolab.settings_service import load_settings
from petrolab.storage import ensure_storage
from petrolab.ui.image_page_policy import install as install_image_page_policy
from petrolab.ui.navigation import render_sidebar
from petrolab.ui.pages import (
    render_analyses_page,
    render_article_tables_page,
    render_change_log_page,
    render_export_page,
    render_formulae_page,
    render_help_page,
    render_home_page,
    render_images_page,
    render_minerals_page,
    render_plots_page,
    render_projects_page,
    render_rocks_page,
    render_science_plots_page,
    render_settings_page,
    render_sources_page,
    render_statistics_page,
    render_ternary_page,
    render_updates_page,
)
from petrolab.ui.science_page_policy import install as install_science_page_policy
from petrolab.ui.theme import apply_theme


st.set_page_config(page_title="ПетроЛаб", page_icon="◈", layout="wide")
install_science_page_policy()
install_image_page_policy()
ensure_storage()
settings = load_settings()
apply_theme(str(settings.get("ui_density", "comfortable")))
st.session_state.setdefault("loaded_recipe", None)
st.session_state.setdefault("loaded_ternary_recipe", None)


def _reconcile_plot_recipe_state() -> None:
    recipe = st.session_state.get("loaded_recipe")
    payload = recipe if isinstance(recipe, dict) else {}
    token = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    ).hexdigest() if payload else ""
    token_key = "_applied_plot_recipe_token"
    previous = str(st.session_state.get(token_key, ""))
    if token == previous:
        return
    if token or previous:
        exact = {
            "plot_datasets", "plot_minerals", "plot_search", "column_filter_columns",
            "journal_preset", "plot_range_columns", "outlier_method", "outlier_columns",
            "outlier_threshold", "exclude_auto_outliers", "manual_outlier_exclusions",
            "outlier_scope", "outlier_scope_group", "keep_hidden_manual_exclusions",
            "style_profile_select", "interactive_selected_point",
            "petrolab_advanced_interactive_plot",
        }
        prefixes = ("filter_vals_", "range_low_", "range_high_", "style_editor_")
        for key in list(st.session_state):
            text = str(key)
            if text in exact or any(text.startswith(prefix) for prefix in prefixes):
                del st.session_state[key]
    cfg = payload.get("outlier_filters", {}) if payload else {}
    if not isinstance(cfg, dict):
        cfg = {}
    st.session_state.plot_interactive_excluded_ids = list(cfg.get("interactive_excluded_ids", []))
    st.session_state[token_key] = token


_reconcile_plot_recipe_state()

ROUTES = {
    "home": render_home_page,
    "sources": render_sources_page,
    "analyses": render_analyses_page,
    "formulae": render_formulae_page,
    "plots": render_plots_page,
    "ternary": render_ternary_page,
    "science_plots": render_science_plots_page,
    "statistics": render_statistics_page,
    "rocks": render_rocks_page,
    "images": render_images_page,
    "minerals": render_minerals_page,
    "article_tables": render_article_tables_page,
    "export": render_export_page,
    "projects": render_projects_page,
    "settings": render_settings_page,
    "help": render_help_page,
    "updates": render_updates_page,
    "change_log": render_change_log_page,
}

with st.sidebar:
    route = render_sidebar(__version__)

ROUTES.get(route, render_home_page)()
