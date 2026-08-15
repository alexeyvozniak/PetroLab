from __future__ import annotations

import hashlib
import json

import streamlit as st

from petrolab import __version__
from petrolab.settings_service import load_settings
from petrolab.storage import ensure_storage
from petrolab.ui.navigation import render_sidebar
from petrolab.ui.pages import (
    render_add_data_page, render_analyses_page, render_analytical_sessions_page,
    render_article_tables_page, render_attention_page, render_batch_edit_page,
    render_calculate_page, render_change_log_page, render_collaboration_page,
    render_compare_page, render_composite_points_page, render_data_intake_page,
    render_database_browser_page, render_distribution_page, render_equilibrium_page,
    render_export_page, render_formulae_page, render_generations_page,
    render_global_search_page, render_guided_workflow_page, render_help_page,
    render_home_page, render_images_page, render_measurements_page,
    render_minerals_page, render_mixed_minerals_page, render_multi_panel_page,
    render_object_workspace_page, render_plots_page, render_projects_page,
    render_publish_page, render_quick_import_page, render_rock_workspace_page,
    render_rocks_page, render_science_plots_page, render_settings_page, render_slides_page,
    render_sources_page, render_statistics_page, render_ternary_page,
    render_thermobarometry_page, render_thin_section_workspace_page, render_updates_page,
    render_whole_rock_compare_page,
)
from petrolab.ui.release_chrome import apply_release_chrome
from petrolab.ui.theme import apply_theme
from petrolab.ui.workflow_routing import apply_smart_plot_defaults, route_fresh_import_to_workflow


st.set_page_config(page_title="ПетроЛаб", page_icon="◈", layout="wide")
ensure_storage()
settings = load_settings()
apply_theme(str(settings.get("ui_density", "comfortable")))
apply_release_chrome()
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
            "style_profile_select", "interactive_selected_point", "petrolab_advanced_interactive_plot",
            "advanced_plot_visible_sources",
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
route_fresh_import_to_workflow()
apply_smart_plot_defaults()

ROUTES = {
    "home": render_home_page, "search": render_global_search_page,
    "workspace": render_object_workspace_page, "thin_section": render_thin_section_workspace_page,
    "composite_points": render_composite_points_page, "multi_panel": render_multi_panel_page,
    "rock_workspace": render_rock_workspace_page,
    "whole_rock_compare": render_whole_rock_compare_page,
    "compare": render_compare_page, "calculate": render_calculate_page, "publish": render_publish_page,
    "workflow": render_guided_workflow_page, "add_data": render_add_data_page,
    "quick_import": render_quick_import_page,
    "attention": render_attention_page, "batch_edit": render_batch_edit_page,
    "intake": render_data_intake_page, "sessions": render_analytical_sessions_page,
    "mixed_minerals": render_mixed_minerals_page, "measurements": render_measurements_page,
    "database": render_database_browser_page, "sources": render_sources_page,
    "analyses": render_analyses_page, "formulae": render_formulae_page,
    "plots": render_plots_page, "ternary": render_ternary_page,
    "thermobarometry": render_thermobarometry_page, "equilibrium": render_equilibrium_page,
    "distribution": render_distribution_page, "science_plots": render_science_plots_page,
    "statistics": render_statistics_page, "generations": render_generations_page,
    "rocks": render_rocks_page, "slides": render_slides_page, "images": render_images_page,
    "minerals": render_minerals_page, "article_tables": render_article_tables_page,
    "export": render_export_page, "projects": render_projects_page,
    "collaboration": render_collaboration_page, "settings": render_settings_page,
    "help": render_help_page, "updates": render_updates_page,
    "change_log": render_change_log_page,
}

with st.sidebar:
    route = render_sidebar(__version__)

ROUTES.get(route, render_home_page)()
