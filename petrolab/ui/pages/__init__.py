"""Streamlit page renderers.

v0.15.7 keeps compatibility wrappers only where their behaviour has not yet
been moved into a canonical page/component. Home, Workspace, Add Data, editor,
article tables, batch actions, XY and analytical multi-panel are direct renderers.
"""

from .add_data import render_add_data_page
from .analyses_dashboard import render_analyses_dashboard_page as render_analyses_page
from .analytical_sessions import render_analytical_sessions_page
from .article_tables import render_article_tables_page
from .attention import render_attention_page
from .batch_edit import render_batch_edit_page
from .change_log import render_change_log_page
from .collaboration import render_collaboration_page
from .composite_points import render_composite_points_page
from .data_intake import render_data_intake_page
from .database_browser import render_database_browser_page
from .distribution import render_distribution_page
from .equilibrium import render_equilibrium_page
from .export import render_export_page
from .formulae import render_formulae_page
from .generations import render_generations_page
from .global_search import render_global_search_page
from .grain_profile import render_grain_profile_page
from .guided_workflow import render_guided_workflow_page
from .help import render_help_page
from .home_dashboard import render_home_dashboard_page as render_home_page
from .images_dashboard import render_images_dashboard_page as render_images_page
from .measurements import render_measurements_page
from .minerals import render_minerals_page
from .mixed_minerals import render_mixed_minerals_page
from .multi_panel import render_multi_panel_page
from .object_workspace import render_object_workspace_page
from .plots_dashboard import render_plots_dashboard_page as render_plots_page
from .projects import render_projects_page
from .publication_composer import render_publication_composer_page
from .quick_import import render_quick_import_page
from .rock_workspace import render_rock_workspace_page
from .rocks import render_rocks_page
from .scenario_hubs import render_calculate_page, render_compare_page, render_publish_page
from .science_plots import render_science_plots_page
from .settings import render_settings_page
from .slides import render_slides_page
from .sources_dashboard import render_sources_dashboard_page as render_sources_page
from .statistics import render_statistics_page
from .ternary import render_ternary_page
from .thermobarometry import render_thermobarometry_page
from .thin_section_workspace import render_thin_section_workspace_page
from .updates import render_updates_page
from .whole_rock_compare import render_whole_rock_compare_page

# Compatibility wrappers still needed for exact global-search/thin-section and
# physical-point workflows. Canonical Add Data, XY and multi-panel intentionally
# do NOT come from this release layer anymore.
from .v0151_wrappers import (
    render_composite_points_page,
    render_global_search_page,
    render_thin_section_workspace_page,
)

# Grain-profile entry from global search is still a compatibility extension.
from .v0153_grain_profile_wrappers import render_global_search_page

# Rock workspace compatibility remains until the whole-rock staging path is
# consolidated separately.
from .v0154_rock_workspace_wrappers import render_rocks_page
from .rocks_staging_bridge_v0154 import render_rocks_page
from .whole_rock_compare_linked_v0154 import render_whole_rock_compare_page

# Remaining cross-page audit wrappers only own contracts not yet absorbed by
# their canonical pages: destructive formula actions and exact object routing.
from .v0156_audit_wrappers import (
    render_formulae_page,
    render_global_search_page,
    render_guided_workflow_page,
    render_images_page,
    render_mixed_minerals_page,
    render_slides_page,
    render_thin_section_workspace_page,
)

# Post-release UX consolidation: keep selection/editing on one Workspace page,
# remove duplicate workbook controls, make the image step explicit and keep plot
# dataset labels readable. Phase review gets an additional queue guard below.
from .v0160_user_ux_hotfix import (
    render_add_data_page,
    render_mixed_minerals_page,
    render_object_workspace_page,
    render_plots_page,
)
from .v0160_phase_queue_hotfix import render_mixed_minerals_page

__all__ = [
    "render_add_data_page", "render_analyses_page", "render_analytical_sessions_page",
    "render_article_tables_page", "render_attention_page", "render_batch_edit_page",
    "render_calculate_page", "render_change_log_page", "render_collaboration_page",
    "render_compare_page", "render_composite_points_page", "render_data_intake_page",
    "render_database_browser_page", "render_distribution_page", "render_equilibrium_page",
    "render_export_page", "render_formulae_page", "render_generations_page",
    "render_global_search_page", "render_grain_profile_page", "render_guided_workflow_page",
    "render_help_page", "render_home_page", "render_images_page", "render_measurements_page",
    "render_minerals_page", "render_mixed_minerals_page", "render_multi_panel_page",
    "render_object_workspace_page", "render_plots_page", "render_projects_page",
    "render_publication_composer_page", "render_publish_page", "render_quick_import_page",
    "render_rock_workspace_page", "render_rocks_page", "render_science_plots_page",
    "render_settings_page", "render_slides_page", "render_sources_page", "render_statistics_page",
    "render_ternary_page", "render_thermobarometry_page",
    "render_thin_section_workspace_page", "render_updates_page",
    "render_whole_rock_compare_page",
]
