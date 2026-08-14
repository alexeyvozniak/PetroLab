from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
app_path = ROOT / "app.py"
app_text = app_path.read_text(encoding="utf-8")
pages_dir = ROOT / "petrolab" / "ui" / "pages"
ui_dir = ROOT / "petrolab" / "ui"

for forbidden in [
    "import pandas", "import matplotlib", "def compute_changes", "def apply_quick_filter",
    "def build_scatter", "calculate_formula(", "load_unified_analyses(", "st.data_editor(",
    "st.file_uploader(", "sync_cell_changes", "uuid4()",
]:
    assert forbidden not in app_text, f"{forbidden} leaked back into app.py"

for renderer in [
    "render_home_page", "render_projects_page", "render_sources_page", "render_analyses_page",
    "render_formulae_page", "render_plots_page", "render_ternary_page", "render_images_page",
    "render_minerals_page", "render_export_page", "render_change_log_page",
    "render_science_plots_page", "render_statistics_page", "render_rocks_page",
    "render_article_tables_page", "render_updates_page", "render_settings_page", "render_help_page",
]:
    assert renderer in app_text

for page_name in [
    "projects.py", "formulae.py", "plots.py", "plots_advanced.py",
    "ternary.py", "plots_ternary.py", "minerals.py", "export.py", "change_log.py",
    "science_plots.py", "statistics.py", "rocks.py", "article_tables.py", "updates.py",
    "settings.py", "help.py", "home_dashboard.py", "sources_dashboard.py",
    "analyses_dashboard.py", "plots_dashboard.py", "images_dashboard.py",
]:
    assert (pages_dir / page_name).exists(), page_name

# Dashboard migrations are authoritative: removed renderers/policies must not return.
for obsolete in [
    pages_dir / "home.py",
    pages_dir / "sources.py",
    pages_dir / "analyses.py",
    pages_dir / "images.py",
    ui_dir / "import_page_policy.py",
    ui_dir / "plot_page_policy.py",
    ui_dir / "image_page_policy.py",
]:
    assert not obsolete.exists(), f"obsolete UI layer returned: {obsolete.name}"
for bootstrap in [
    "install_import_page_policy", "install_plot_page_policy", "install_destructive_page_policy",
    "install_image_page_policy",
]:
    assert bootstrap not in app_text, bootstrap

components = ui_dir / "components.py"
components_text = components.read_text(encoding="utf-8")
for function_name in ["def render_project_selector(", "def collect_related_images(", "def render_asset_gallery("]:
    assert function_name in components_text
project_context = ui_dir / "project_context.py"
assert project_context.exists()
project_context_text = project_context.read_text(encoding="utf-8")
for function_name in ["def active_project(", "def active_project_id(", "def set_active_project("]:
    assert function_name in project_context_text
ternary_controls = ui_dir / "ternary_controls.py"
assert ternary_controls.exists()
assert "def render_ternary_selection(" in ternary_controls.read_text(encoding="utf-8")
for ui_file in [
    "data_scope.py", "plot_style_controls.py", "rock_plots.py", "theme.py", "layout.py",
    "navigation.py", "project_context.py", "destructive_actions.py", "xy_components.py",
    "analysis_components.py", "image_components.py", "plot_actions.py",
]:
    assert (ui_dir / ui_file).exists(), ui_file

pure_files = [
    ROOT / "petrolab" / "column_schema.py", ROOT / "petrolab" / "measurement_semantics.py",
    ROOT / "petrolab" / "dataframe_utils.py", ROOT / "petrolab" / "outliers.py",
    ROOT / "petrolab" / "derived.py", ROOT / "petrolab" / "analysis_groups.py",
    ROOT / "petrolab" / "interactive_plotting.py", ROOT / "petrolab" / "plot_presets.py",
    ROOT / "petrolab" / "visualization_presets.py", ROOT / "petrolab" / "extended_plotting.py",
    ROOT / "petrolab" / "scientific_overlays.py", ROOT / "petrolab" / "scientific_plotting.py",
    ROOT / "petrolab" / "statistics.py", ROOT / "petrolab" / "article_tables.py",
    ROOT / "petrolab" / "rock_plotting.py", ROOT / "petrolab" / "storage_extensions.py",
    ROOT / "petrolab" / "ternary_data.py", ROOT / "petrolab" / "ternary_presets.py",
    ROOT / "petrolab" / "ternary_overlays.py", ROOT / "petrolab" / "ternary_plotting.py",
    ROOT / "petrolab" / "analysis_identity.py",
    ROOT / "petrolab" / "services" / "import_service.py",
    ROOT / "petrolab" / "services" / "analysis_service.py",
    ROOT / "petrolab" / "services" / "formula_service.py",
    ROOT / "petrolab" / "services" / "image_service.py",
    ROOT / "petrolab" / "services" / "rock_service.py",
    ROOT / "petrolab" / "services" / "rock_image_service.py",
    ROOT / "petrolab" / "repositories" / "analysis_repository.py",
    ROOT / "petrolab" / "repositories" / "analysis_refresh_repository.py",
    ROOT / "petrolab" / "repositories" / "image_repository.py",
    ROOT / "petrolab" / "repositories" / "rock_repository.py",
    *sorted((ROOT / "petrolab" / "minerals").rglob("*.py")),
]
for path in pure_files:
    text = path.read_text(encoding="utf-8")
    assert "import streamlit" not in text, f"Streamlit dependency leaked into {path}"
    assert "from streamlit" not in text, f"Streamlit dependency leaked into {path}"

science_page_text = (pages_dir / "science_plots.py").read_text(encoding="utf-8")
science_overlay_text = (ROOT / "petrolab" / "scientific_overlays.py").read_text(encoding="utf-8")
for coefficient in ["51.9078", "52.8316", "3.375", "0.94"]:
    assert coefficient in science_overlay_text
    assert coefficient not in science_page_text, f"scientific coefficient {coefficient} leaked into UI"
assert "10.1016/j.lithos.2004.04.025" in science_overlay_text
assert "10.1016/j.lithos.2004.04.012" in science_overlay_text

overlay_text = (ROOT / "petrolab" / "ternary_overlays.py").read_text(encoding="utf-8")
preset_text = (ROOT / "petrolab" / "ternary_presets.py").read_text(encoding="utf-8")
plotting_text = (ROOT / "petrolab" / "ternary_plotting.py").read_text(encoding="utf-8")
classification_text = (ROOT / "petrolab" / "minerals" / "classification.py").read_text(encoding="utf-8")
for scientific_name in [
    "Pigeonite", "Augite", "Diopside", "Hedenbergite", "Oligoclase", "Andesine",
    "Labradorite", "Bytownite", "Prp-dominant", "Alm-dominant", "Grs-dominant",
    "Sps-dominant", "Schorlomite", "Morimotoite",
]:
    assert scientific_name in overlay_text or scientific_name in classification_text
    assert scientific_name not in plotting_text, f"{scientific_name} leaked into generic renderer"
for overlay_id in [
    "pyroxene_morimoto_1988", "feldspar_gunduz_asan_2023",
    "garnet_prp_alm_grs_dominance", "garnet_prp_alm_sps_dominance", "garnet_ti_grew2013_fig5",
]:
    assert overlay_id in overlay_text
    assert f'field_overlay_id="{overlay_id}"' in preset_text
assert "source_citation" in overlay_text and "source_doi" in overlay_text
assert "TiO2 > 12" in preset_text
assert "def attach_mineral_classification(" in classification_text
assert "def attach_garnet_ima_diagnostics(" in classification_text

formula_service = (ROOT / "petrolab" / "services" / "formula_service.py").read_text(encoding="utf-8")
assert "attach_mineral_classification" in formula_service and "final = attach_mineral_classification(" in formula_service
import_service = (ROOT / "petrolab" / "services" / "import_service.py").read_text(encoding="utf-8")
for function_name in ["def import_linked_sheets(", "def import_uploaded_sheets(", "def refresh_dataset_from_source("]:
    assert function_name in import_service
assert "apply_measurement_overrides" in import_service
formula_page = (pages_dir / "formulae.py").read_text(encoding="utf-8")
assert "save_formula_results" in formula_page and "calculate_formula_safe" in formula_page

# XY implementation lives in dashboard/advanced/components; plots.py is only a tiny guarded-action facade for now.
plots_facade = (pages_dir / "plots.py").read_text(encoding="utf-8")
assert "def render_plots_page(" not in plots_facade
assert "load_unified_with_derived" not in plots_facade
for marker in ["delete_plot_recipe", "delete_style_profile", "clear_work_group", "confirm_then"]:
    assert marker in plots_facade, marker
plots_advanced = (pages_dir / "plots_advanced.py").read_text(encoding="utf-8")
for marker in ["load_unified_with_derived", "render_outlier_controls", "render_advanced_interactive", "save_plot_recipe"]:
    assert marker in plots_advanced, marker
xy_components = (ui_dir / "xy_components.py").read_text(encoding="utf-8")
for marker in ["robust_outliers", "manual_outlier_exclusions", "build_interactive_scatter", "selected_analysis_ids", "set_work_group", "st.plotly_chart"]:
    assert marker in xy_components, marker

# Analysis and image dashboards now own their UI directly.
analyses_dashboard = (pages_dir / "analyses_dashboard.py").read_text(encoding="utf-8")
for marker in ["analysis_components", "load_unified_with_derived", "active_derived_columns", "attach_work_groups"]:
    assert marker in analyses_dashboard, marker
assert "from petrolab.ui.pages import analyses" not in analyses_dashboard
images_dashboard = (pages_dir / "images_dashboard.py").read_text(encoding="utf-8")
for marker in ["image_components", "create_assigned_image_batch", "relink_image_asset", "active_project_id"]:
    assert marker in images_dashboard, marker
assert "from petrolab.ui.pages import images" not in images_dashboard
assert "render_project_selector" not in images_dashboard

ternary_page = (pages_dir / "ternary.py").read_text(encoding="utf-8")
ternary_workspace = (pages_dir / "plots_ternary.py").read_text(encoding="utf-8")
assert "load_unified_with_derived" in ternary_page and "render_ternary_workspace" in ternary_page
for marker in ["prepare_ternary", "render_ternary_selection", "attach_ternary_classification", "build_interactive_ternary", "build_publication_ternary", "selected_analysis_ids", "save_plot_recipe"]:
    assert marker in ternary_workspace
rocks_page = (pages_dir / "rocks.py").read_text(encoding="utf-8")
for marker in ["_set_mineral_links", "replace_isotopes", "render_rock_plots", "delete_rock_with_assets", "confirm_then"]:
    assert marker in rocks_page
assert "render_project_selector" not in rocks_page
assert "active_project_id" in rocks_page and "render_page_header" in rocks_page
statistics_module = (ROOT / "petrolab" / "statistics.py").read_text(encoding="utf-8")
assert "KMeans" in statistics_module and "PCA" in statistics_module
assert "analysis_rows" not in statistics_module, "statistics core must not write analytical storage"

for path in [app_path, *sorted((ROOT / "petrolab").rglob("*.py"))]:
    text = path.read_text(encoding="utf-8")
    assert re.search(r"^\s*except\s*:\s*$", text, flags=re.MULTILINE) is None, f"bare except in {path}"

for path in (ROOT / "tools").glob("patch_*.py") if (ROOT / "tools").exists() else []:
    raise AssertionError(f"temporary patch script remains: {path.name}")

app_lines = len(app_text.splitlines())
assert app_lines <= 120, f"app.py grew to {app_lines} lines; keep workspace code in page modules"
assert "PAGE_GROUPS" not in app_text
assert "render_sidebar" in app_text and "ROUTES" in app_text
assert (ROOT / "CONTRIBUTING.md").exists() and (ROOT / "ARCHITECTURE.md").exists()
print(f"architecture tests: OK; app.py = {app_lines} lines")
