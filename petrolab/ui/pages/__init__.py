"""Streamlit page renderers."""

from .add_data import render_add_data_page
from .analyses_dashboard import render_analyses_dashboard_page as render_analyses_page
from .analytical_sessions import render_analytical_sessions_page
from .article_tables import render_article_tables_page
from .attention import render_attention_page
from .batch_edit import render_batch_edit_page
from .change_log import render_change_log_page
from .collaboration import render_collaboration_page
from .data_intake import render_data_intake_page
from .database_browser import render_database_browser_page
from .distribution import render_distribution_page
from .equilibrium import render_equilibrium_page
from .export import render_export_page
from .formulae import render_formulae_page
from .generations import render_generations_page
from .guided_workflow import render_guided_workflow_page
from .help import render_help_page
from .home_dashboard import render_home_dashboard_page as render_home_page
from .images_dashboard import render_images_dashboard_page as render_images_page
from .measurements import render_measurements_page
from .minerals import render_minerals_page
from .mixed_minerals import render_mixed_minerals_page
from .object_workspace import render_object_workspace_page
from .plots_dashboard import render_plots_dashboard_page as render_plots_page
from .projects import render_projects_page
from .rocks import render_rocks_page
from .science_plots import render_science_plots_page
from .settings import render_settings_page
from .slides import render_slides_page
from .sources_dashboard import render_sources_dashboard_page as render_sources_page
from .statistics import render_statistics_page
from .ternary import render_ternary_page
from .thermobarometry import render_thermobarometry_page
from .updates import render_updates_page

__all__ = [
    "render_add_data_page", "render_analyses_page", "render_analytical_sessions_page",
    "render_article_tables_page", "render_attention_page", "render_batch_edit_page",
    "render_change_log_page", "render_collaboration_page", "render_data_intake_page",
    "render_database_browser_page", "render_distribution_page", "render_equilibrium_page",
    "render_export_page", "render_formulae_page", "render_generations_page",
    "render_guided_workflow_page", "render_help_page", "render_home_page",
    "render_images_page", "render_measurements_page", "render_minerals_page",
    "render_mixed_minerals_page", "render_object_workspace_page", "render_plots_page",
    "render_projects_page", "render_rocks_page", "render_science_plots_page",
    "render_settings_page", "render_slides_page", "render_sources_page", "render_statistics_page",
    "render_ternary_page", "render_thermobarometry_page", "render_updates_page",
]
