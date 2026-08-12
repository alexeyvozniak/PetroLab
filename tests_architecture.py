from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
app_path = ROOT / "app.py"
app_text = app_path.read_text(encoding="utf-8")
pages_dir = ROOT / "petrolab" / "ui" / "pages"

# app.py is now deliberately only navigation/integration, not a workspace implementation.
for forbidden in [
    "import pandas",
    "import matplotlib",
    "def compute_changes",
    "def apply_quick_filter",
    "def build_scatter",
    "calculate_formula(",
    "load_unified_analyses(",
    "st.data_editor(",
    "st.file_uploader(",
    "sync_cell_changes",
    "uuid4()",
]:
    assert forbidden not in app_text, f"{forbidden} leaked back into app.py"

for renderer in [
    "render_home_page",
    "render_projects_page",
    "render_sources_page",
    "render_analyses_page",
    "render_formulae_page",
    "render_plots_page",
    "render_ternary_page",
    "render_images_page",
    "render_minerals_page",
    "render_export_page",
    "render_change_log_page",
]:
    assert renderer in app_text

for page_name in [
    "home.py",
    "projects.py",
    "sources.py",
    "analyses.py",
    "formulae.py",
    "plots.py",
    "ternary.py",
    "plots_ternary.py",
    "images.py",
    "minerals.py",
    "export.py",
    "change_log.py",
]:
    assert (pages_dir / page_name).exists(), page_name

# Shared UI helpers stay in one component module.
components = ROOT / "petrolab" / "ui" / "components.py"
components_text = components.read_text(encoding="utf-8")
for function_name in [
    "def render_project_selector(",
    "def collect_related_images(",
    "def render_asset_gallery(",
]:
    assert function_name in components_text

# Service/data layers remain usable independently from Streamlit.
pure_files = [
    ROOT / "petrolab" / "column_schema.py",
    ROOT / "petrolab" / "measurement_semantics.py",
    ROOT / "petrolab" / "dataframe_utils.py",
    ROOT / "petrolab" / "outliers.py",
    ROOT / "petrolab" / "derived.py",
    ROOT / "petrolab" / "analysis_groups.py",
    ROOT / "petrolab" / "interactive_plotting.py",
    ROOT / "petrolab" / "plot_presets.py",
    ROOT / "petrolab" / "ternary_data.py",
    ROOT / "petrolab" / "ternary_presets.py",
    ROOT / "petrolab" / "ternary_plotting.py",
    ROOT / "petrolab" / "analysis_identity.py",
    ROOT / "petrolab" / "services" / "import_service.py",
    ROOT / "petrolab" / "services" / "analysis_service.py",
    ROOT / "petrolab" / "services" / "formula_service.py",
    ROOT / "petrolab" / "services" / "image_service.py",
    ROOT / "petrolab" / "repositories" / "analysis_repository.py",
    ROOT / "petrolab" / "repositories" / "analysis_refresh_repository.py",
    ROOT / "petrolab" / "repositories" / "image_repository.py",
    *sorted((ROOT / "petrolab" / "minerals").rglob("*.py")),
]
for path in pure_files:
    text = path.read_text(encoding="utf-8")
    assert "import streamlit" not in text, f"Streamlit dependency leaked into {path}"
    assert "from streamlit" not in text, f"Streamlit dependency leaked into {path}"

# Key workflows must be represented explicitly in the right layer.
import_service = (ROOT / "petrolab" / "services" / "import_service.py").read_text(encoding="utf-8")
for function_name in [
    "def import_linked_sheets(",
    "def import_uploaded_sheets(",
    "def refresh_dataset_from_source(",
]:
    assert function_name in import_service
assert "apply_measurement_overrides" in import_service

formula_page = (pages_dir / "formulae.py").read_text(encoding="utf-8")
assert "save_formula_results" in formula_page
assert "calculate_formula_safe" in formula_page

plots_page = (pages_dir / "plots.py").read_text(encoding="utf-8")
assert "load_unified_with_derived" in plots_page
assert "robust_outliers" in plots_page
assert "manual_outlier_exclusions" in plots_page
assert "build_interactive_scatter" in plots_page
assert "selected_analysis_ids" in plots_page
assert "set_work_group" in plots_page
assert "st.plotly_chart" in plots_page

ternary_page = (pages_dir / "ternary.py").read_text(encoding="utf-8")
ternary_workspace = (pages_dir / "plots_ternary.py").read_text(encoding="utf-8")
assert "load_unified_with_derived" in ternary_page
assert "render_ternary_workspace" in ternary_page
assert "prepare_ternary" in ternary_workspace
assert "build_interactive_ternary" in ternary_workspace
assert "build_publication_ternary" in ternary_workspace
assert "selected_analysis_ids" in ternary_workspace
assert "save_plot_recipe" in ternary_workspace

analyses_page = (pages_dir / "analyses.py").read_text(encoding="utf-8")
assert "load_unified_with_derived" in analyses_page
assert "active_derived_columns" in analyses_page
assert "attach_work_groups" in analyses_page

# Empty exception handlers make scientific/data failures impossible to diagnose.
for path in [app_path, *sorted((ROOT / "petrolab").rglob("*.py"))]:
    text = path.read_text(encoding="utf-8")
    assert re.search(r"^\s*except\s*:\s*$", text, flags=re.MULTILINE) is None, f"bare except in {path}"

# Temporary patch/workflow machinery must not survive into a production refactor.
for path in (ROOT / "tools").glob("patch_*.py") if (ROOT / "tools").exists() else []:
    raise AssertionError(f"temporary patch script remains: {path.name}")
for path in (ROOT / ".github" / "workflows").glob("apply-*.yml"):
    raise AssertionError(f"temporary apply workflow remains: {path.name}")
for path in (ROOT / ".github" / "workflows").glob("finalize-*.yml"):
    raise AssertionError(f"temporary finalize workflow remains: {path.name}")
for path in (ROOT / ".github" / "workflows").glob("pr-final-verification*.yml"):
    raise AssertionError(f"temporary verification workflow remains: {path.name}")

app_lines = len(app_text.splitlines())
assert app_lines <= 120, f"app.py grew to {app_lines} lines; keep workspace code in page modules"

assert (ROOT / "CONTRIBUTING.md").exists()
assert (ROOT / "ARCHITECTURE.md").exists()
print(f"architecture tests: OK; app.py = {app_lines} lines")
