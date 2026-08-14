"""Streamlit page renderers."""

from .analyses_dashboard import render_analyses_dashboard_page as render_analyses_page
from .article_tables import render_article_tables_page
from .change_log import render_change_log_page
from .data_intake import render_data_intake_page
from .database_browser import render_database_browser_page
from .export import render_export_page
from .formulae import render_formulae_page
from .help import render_help_page
from .home_dashboard import render_home_dashboard_page as render_home_page
from .images_dashboard import render_images_dashboard_page as render_images_page
from .minerals import render_minerals_page
from .mixed_minerals import render_mixed_minerals_page
from .plots_dashboard import render_plots_dashboard_page as render_plots_page
from .projects import render_projects_page
from .rocks import render_rocks_page
from .science_plots import render_science_plots_page
from .settings import render_settings_page
from .sources_dashboard import render_sources_dashboard_page as render_sources_page
from .statistics import render_statistics_page
from .ternary import render_ternary_page
from .updates import render_updates_page

__all__ = [
    "render_analyses_page", "render_article_tables_page", "render_change_log_page",
    "render_data_intake_page", "render_database_browser_page", "render_export_page", "render_formulae_page",
    "render_help_page", "render_home_page", "render_images_page", "render_minerals_page", "render_mixed_minerals_page",
    "render_plots_page", "render_projects_page", "render_rocks_page", "render_science_plots_page",
    "render_settings_page", "render_sources_page", "render_statistics_page",
    "render_ternary_page", "render_updates_page",
]
