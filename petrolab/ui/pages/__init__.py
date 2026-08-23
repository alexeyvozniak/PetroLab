"""Streamlit page renderers with lazy imports.

Keeping this package lightweight matters for startup: importing ``petrolab.ui.pages``
should not initialize every scientific page, plotting stack and sklearn-backed tool
before the first PetroLab screen is visible.
"""
from __future__ import annotations

from importlib import import_module


_LAZY_RENDERERS: dict[str, tuple[str, str]] = {
    "render_add_data_page": (".add_data", "render_add_data_page"),
    "render_analyses_page": (".analyses_dashboard", "render_analyses_dashboard_page"),
    "render_analytical_sessions_page": (".analytical_sessions", "render_analytical_sessions_page"),
    "render_article_tables_page": (".article_tables", "render_article_tables_page"),
    "render_attention_page": (".attention", "render_attention_page"),
    "render_batch_edit_page": (".batch_edit", "render_batch_edit_page"),
    "render_change_log_page": (".change_log", "render_change_log_page"),
    "render_collaboration_page": (".collaboration", "render_collaboration_page"),
    "render_data_intake_page": (".data_intake", "render_data_intake_page"),
    "render_database_browser_page": (".database_browser", "render_database_browser_page"),
    "render_distribution_page": (".distribution", "render_distribution_page"),
    "render_equilibrium_page": (".equilibrium", "render_equilibrium_page"),
    "render_export_page": (".export", "render_export_page"),
    "render_figure_recipes_page": (".figure_recipes", "render_figure_recipes_page"),
    "render_formulae_page": (".formulae", "render_formulae_page"),
    "render_generations_page": (".generations", "render_generations_page"),
    "render_guided_workflow_page": (".guided_workflow", "render_guided_workflow_page"),
    "render_help_page": (".help", "render_help_page"),
    "render_home_page": (".home_dashboard", "render_home_dashboard_page"),
    "render_images_page": (".images_dashboard", "render_images_dashboard_page"),
    "render_linked_views_page": (".linked_views", "render_linked_views_page"),
    "render_measurements_page": (".measurements", "render_measurements_page"),
    "render_minerals_page": (".minerals", "render_minerals_page"),
    "render_mixed_minerals_page": (".mixed_minerals", "render_mixed_minerals_page"),
    "render_plots_page": (".plots_dashboard", "render_plots_dashboard_page"),
    "render_projects_page": (".projects", "render_projects_page"),
    "render_rocks_page": (".rocks", "render_rocks_page"),
    "render_science_plots_page": (".science_plots", "render_science_plots_page"),
    "render_search_page": (".search", "render_search_page"),
    "render_selections_page": (".selections", "render_selections_page"),
    "render_settings_page": (".settings", "render_settings_page"),
    "render_slides_page": (".slides", "render_slides_page"),
    "render_sources_page": (".sources_dashboard", "render_sources_dashboard_page"),
    "render_statistics_page": (".v0160_cluster_statistics_hotfix", "render_statistics_page"),
    "render_ternary_page": (".ternary", "render_ternary_page"),
    "render_thermobarometry_page": (".thermobarometry", "render_thermobarometry_page"),
    "render_updates_page": (".updates", "render_updates_page"),
}

__all__ = list(_LAZY_RENDERERS)


def __getattr__(name: str):
    try:
        module_name, attribute = _LAZY_RENDERERS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    module = import_module(module_name, __name__)
    value = getattr(module, attribute)
    globals()[name] = value
    return value
