from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent
app_path = ROOT / "app.py"
app_text = app_path.read_text(encoding="utf-8")
pages_dir = ROOT / "petrolab" / "ui" / "pages"
ui_dir = ROOT / "petrolab" / "ui"

# app.py remains a lightweight shell. Scientific/data-heavy modules are resolved
# only for the route that the user actually opens.
for forbidden in [
    "import pandas", "import matplotlib", "def compute_changes", "def apply_quick_filter",
    "def build_scatter", "calculate_formula(", "load_unified_analyses(", "st.data_editor(",
    "st.file_uploader(", "sync_cell_changes", "uuid4()",
]:
    assert forbidden not in app_text, f"{forbidden} leaked back into app.py"

for marker in [
    "from importlib import import_module",
    "ROUTE_TARGETS",
    "def _resolve_renderer(",
    "import_module(module_path)",
    "@st.cache_resource(show_spinner=False)",
    "render_sidebar",
]:
    assert marker in app_text, marker

# The screenshot-led Product Design surfaces own their routes explicitly. The
# linked-view route passes through a tiny Plotly compatibility layer while the
# reference page remains the actual workspace implementation.
reference_routes = {
    "add_data_reference.py": '"add_data": ("petrolab.ui.pages.add_data_reference", "render_add_data_reference_page")',
    "linked_views_compat.py": '"linked_views": ("petrolab.ui.pages.linked_views_compat", "render_linked_views_reference_page")',
    "search_reference.py": '"search": ("petrolab.ui.pages.search_reference", "render_search_reference_page")',
    "slides_reference.py": '"slides": ("petrolab.ui.pages.slides_reference", "render_slides_reference_page")',
}
for filename, route_marker in reference_routes.items():
    path = pages_dir / filename
    assert path.exists(), filename
    ast.parse(path.read_text(encoding="utf-8"), filename=filename)
    assert route_marker in app_text, route_marker
assert (pages_dir / "linked_views_reference.py").exists(), "linked reference workspace missing"

# Authoritative page owners remain in place. The visual redesign must not bring
# back the obsolete parallel page/policy layer.
for page_name in [
    "projects.py", "formulae.py", "plots_advanced.py", "ternary.py", "plots_ternary.py",
    "minerals.py", "export.py", "change_log.py", "science_plots.py", "statistics.py",
    "rocks.py", "article_tables.py", "updates.py", "settings.py", "help.py",
    "home_dashboard.py", "sources_dashboard.py", "analyses_dashboard.py",
    "plots_dashboard.py", "images_dashboard.py",
]:
    assert (pages_dir / page_name).exists(), page_name

for obsolete in [
    pages_dir / "home.py", pages_dir / "sources.py", pages_dir / "analyses.py",
    pages_dir / "images.py", pages_dir / "plots.py",
    ui_dir / "import_page_policy.py", ui_dir / "plot_page_policy.py",
    ui_dir / "image_page_policy.py", ui_dir / "science_page_policy.py",
    ui_dir / "destructive_page_policy.py",
]:
    assert not obsolete.exists(), f"obsolete UI layer returned: {obsolete.name}"
assert not list(ui_dir.glob("*_page_policy.py")), "runtime page policy module returned"

# Shared project/selection/destructive-action boundaries survive the UI rebuild.
for ui_file in [
    "data_scope.py", "theme.py", "layout.py", "navigation.py", "navigation_state.py",
    "project_context.py", "destructive_actions.py", "xy_components.py", "analysis_components.py",
    "analysis_table.py", "image_components.py", "plot_actions.py", "plot_spec.py",
    "selection_context.py", "selection_components.py", "linked_panels.py",
]:
    assert (ui_dir / ui_file).exists(), ui_file

project_context_text = (ui_dir / "project_context.py").read_text(encoding="utf-8")
for marker in ["def active_project(", "def active_project_id(", "def set_active_project("]:
    assert marker in project_context_text, marker
selection_context_text = (ui_dir / "selection_context.py").read_text(encoding="utf-8")
for marker in ["class SelectionContext", "replace", "add", "subtract", "class RowStates", "hidden", "excluded"]:
    assert marker in selection_context_text, marker
selection_components_text = (ui_dir / "selection_components.py").read_text(encoding="utf-8")
for marker in ["set_work_group", "clear_work_group", "assign_generation", "read_selection", "set_row_state"]:
    assert marker in selection_components_text, marker

# Scientific/domain cores stay independent of Streamlit.
pure_files = [
    ROOT / "petrolab" / "column_schema.py", ROOT / "petrolab" / "measurement_semantics.py",
    ROOT / "petrolab" / "dataframe_utils.py", ROOT / "petrolab" / "outliers.py",
    ROOT / "petrolab" / "derived.py", ROOT / "petrolab" / "analysis_groups.py",
    ROOT / "petrolab" / "interactive_plotting.py", ROOT / "petrolab" / "extended_plotting.py",
    ROOT / "petrolab" / "scientific_overlays.py", ROOT / "petrolab" / "scientific_plotting.py",
    ROOT / "petrolab" / "statistics.py", ROOT / "petrolab" / "article_tables.py",
    ROOT / "petrolab" / "rock_plotting.py", ROOT / "petrolab" / "ternary_data.py",
    ROOT / "petrolab" / "ternary_plotting.py", ROOT / "petrolab" / "analysis_identity.py",
    ROOT / "petrolab" / "services" / "import_service.py",
    ROOT / "petrolab" / "services" / "analysis_service.py",
    ROOT / "petrolab" / "services" / "formula_service.py",
    ROOT / "petrolab" / "services" / "image_service.py",
    ROOT / "petrolab" / "repositories" / "analysis_repository.py",
    ROOT / "petrolab" / "repositories" / "image_repository.py",
    *sorted((ROOT / "petrolab" / "minerals").rglob("*.py")),
]
for path in pure_files:
    text = path.read_text(encoding="utf-8")
    assert "import streamlit" not in text, f"Streamlit dependency leaked into {path}"
    assert "from streamlit" not in text, f"Streamlit dependency leaked into {path}"

# Scientific coefficients/citations remain in domain overlays, not page UI.
science_page_text = (pages_dir / "science_plots.py").read_text(encoding="utf-8")
science_overlay_text = (ROOT / "petrolab" / "scientific_overlays.py").read_text(encoding="utf-8")
for coefficient in ["51.9078", "52.8316", "3.375", "0.94"]:
    assert coefficient in science_overlay_text
    assert coefficient not in science_page_text
for doi in ["10.1016/j.lithos.2004.04.025", "10.1016/j.lithos.2004.04.012"]:
    assert doi in science_overlay_text

classification_text = (ROOT / "petrolab" / "minerals" / "classification.py").read_text(encoding="utf-8")
for marker in ["def attach_mineral_classification(", "def attach_garnet_ima_diagnostics("]:
    assert marker in classification_text, marker
formula_service = (ROOT / "petrolab" / "services" / "formula_service.py").read_text(encoding="utf-8")
assert "attach_mineral_classification" in formula_service
statistics_text = (ROOT / "petrolab" / "statistics.py").read_text(encoding="utf-8")
assert "KMeans" in statistics_text and "PCA" in statistics_text
assert "analysis_rows" not in statistics_text, "statistics core must not write analytical storage"

app_lines = len(app_text.splitlines())
assert app_lines <= 180, f"app.py grew to {app_lines} lines"
assert "PAGE_GROUPS" not in app_text
assert "ROUTE_TARGETS" in app_text and "render_sidebar" in app_text
assert (ROOT / "CONTRIBUTING.md").exists() and (ROOT / "ARCHITECTURE.md").exists()
print(f"architecture tests: OK; app.py = {app_lines} lines")
