from __future__ import annotations

import hashlib
import json
from importlib import import_module

import streamlit as st

from petrolab import __version__
from petrolab.settings_service import load_settings
from petrolab.storage import ensure_storage
from petrolab.ui.navigation import ROUTE_LABELS, render_sidebar
from petrolab.ui.route_scroll import reset_route_scroll_if_pending
from petrolab.ui.theme import apply_theme
from petrolab.ui.workflow_routing import apply_smart_plot_defaults, route_fresh_import_to_workflow


st.set_page_config(page_title="ПетроЛаб", page_icon="◈", layout="wide")
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
            "style_profile_select", "interactive_selected_point", "petrolab_advanced_interactive_plot",
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


# Keep the first paint lean. Heavy scientific pages load only when opened.
ROUTE_TARGETS: dict[str, tuple[str, str]] = {
    "home": ("petrolab.ui.pages.home_dashboard", "render_home_dashboard_page"),
    "workflow": ("petrolab.ui.pages.guided_workflow", "render_guided_workflow_page"),
    "add_data": ("petrolab.ui.pages.add_data_reference", "render_add_data_reference_page"),
    "attention": ("petrolab.ui.pages.attention", "render_attention_page"),
    "batch_edit": ("petrolab.ui.pages.batch_edit", "render_batch_edit_page"),
    "intake": ("petrolab.ui.pages.data_intake", "render_data_intake_page"),
    "sessions": ("petrolab.ui.pages.analytical_sessions", "render_analytical_sessions_page"),
    "mixed_minerals": ("petrolab.ui.pages.mixed_minerals", "render_mixed_minerals_page"),
    "measurements": ("petrolab.ui.pages.measurements", "render_measurements_page"),
    "samples": ("petrolab.ui.pages.database_reference", "render_database_reference_page"),
    "database": ("petrolab.ui.pages.database_reference", "render_database_reference_page"),
    "sources": ("petrolab.ui.pages.sources_dashboard", "render_sources_dashboard_page"),
    "analyses": ("petrolab.ui.pages.analyses_dashboard", "render_analyses_dashboard_page"),
    "formulae": ("petrolab.ui.pages.formulae", "render_formulae_page"),
    "plots": ("petrolab.ui.pages.plots_dashboard", "render_plots_dashboard_page"),
    "ternary": ("petrolab.ui.pages.ternary", "render_ternary_page"),
    "linked_views": ("petrolab.ui.pages.linked_views_reference", "render_linked_views_reference_page"),
    "thermobarometry": ("petrolab.ui.pages.thermobarometry", "render_thermobarometry_page"),
    "equilibrium": ("petrolab.ui.pages.equilibrium", "render_equilibrium_page"),
    "distribution": ("petrolab.ui.pages.distribution", "render_distribution_page"),
    "science_plots": ("petrolab.ui.pages.science_plots", "render_science_plots_page"),
    "statistics": ("petrolab.ui.pages.statistics_reference", "render_statistics_reference_page"),
    "generations": ("petrolab.ui.pages.generations", "render_generations_page"),
    "rocks": ("petrolab.ui.pages.rocks", "render_rocks_page"),
    "search": ("petrolab.ui.pages.search_reference", "render_search_reference_page"),
    "selections": ("petrolab.ui.pages.selections", "render_selections_page"),
    "slides": ("petrolab.ui.pages.slides_reference", "render_slides_reference_page"),
    "images": ("petrolab.ui.pages.images_dashboard", "render_images_dashboard_page"),
    "minerals": ("petrolab.ui.pages.minerals", "render_minerals_page"),
    "article_tables": ("petrolab.ui.pages.article_tables", "render_article_tables_page"),
    "export": ("petrolab.ui.pages.export_reference", "render_export_reference_page"),
    "figure_recipes": ("petrolab.ui.pages.figure_recipes", "render_figure_recipes_page"),
    "projects": ("petrolab.ui.pages.projects", "render_projects_page"),
    "collaboration": ("petrolab.ui.pages.collaboration", "render_collaboration_page"),
    "settings": ("petrolab.ui.pages.settings", "render_settings_page"),
    "help": ("petrolab.ui.pages.help", "render_help_page"),
    "updates": ("petrolab.ui.pages.updates", "render_updates_page"),
    "change_log": ("petrolab.ui.pages.change_log", "render_change_log_page"),
}


@st.cache_resource(show_spinner=False)
def _resolve_renderer(module_path: str, function_name: str):
    module = import_module(module_path)
    return getattr(module, function_name)


def _render_route(route: str) -> None:
    target = ROUTE_TARGETS.get(route, ROUTE_TARGETS["home"])
    label = ROUTE_LABELS.get(route, "Обзор")
    loaded_routes = set(st.session_state.get("_petrolab_loaded_routes", []))
    cold_load = route not in loaded_routes
    placeholder = st.empty()
    if cold_load:
        placeholder.markdown(
            f"""
            <div class="petrolab-loading-card">
              <div class="petrolab-loading-brand">PetroLab</div>
              <div class="petrolab-loading-title">Открываем «{label}»…</div>
              <div class="petrolab-loading-copy">Подключаем только нужный модуль. Данные остаются локально.</div>
              <div class="petrolab-loading-line"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    renderer = _resolve_renderer(*target)
    if cold_load:
        loaded_routes.add(route)
        st.session_state["_petrolab_loaded_routes"] = sorted(loaded_routes)
        placeholder.empty()
    renderer()


with st.sidebar:
    route = render_sidebar(__version__)

reset_route_scroll_if_pending()
_render_route(route)
