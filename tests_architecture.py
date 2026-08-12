from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
app_text = (ROOT / "app.py").read_text(encoding="utf-8")

# app.py remains an integration/UI layer rather than becoming a utility dumping ground again.
assert "from petrolab.dataframe_utils import (" in app_text
assert "from petrolab.plot_presets import JOURNAL_PRESETS" in app_text
assert "def compute_changes" not in app_text
assert "def apply_quick_filter" not in app_text
assert "def apply_column_filters" not in app_text
assert "def row_identity" not in app_text
assert "JOURNAL_PRESETS = {" not in app_text

# Extracted pages stay outside the entrypoint.
for call in [
    "render_home_page()",
    "render_projects_page()",
    "render_sources_page()",
    "render_analyses_page()",
    "render_images_page()",
]:
    assert call in app_text

for forbidden in [
    'with st.form("new_project"',
    'st.subheader("Новая графическая логика")',
    'st.subheader("Локальный Excel с двусторонней синхронизацией")',
    'st.title("Единая база анализов")',
    'st.title("Изображения и аналитические точки")',
    "def save_dataset(",
    "def safe_copy_upload(",
    "def project_selector(",
    "def collect_related_images(",
    "def render_asset_gallery(",
    "sync_cell_changes",
    "update_analysis_values",
    "compute_changes",
    "ASSETS_DIR",
    "add_image_asset",
    "delete_image_asset",
    "uuid4()",
]:
    assert forbidden not in app_text, f"{forbidden} leaked back into app.py"

for page_name in ["home.py", "projects.py", "sources.py", "analyses.py", "images.py"]:
    assert (ROOT / "petrolab" / "ui" / "pages" / page_name).exists()

# Shared UI helpers stay in one component module.
components = ROOT / "petrolab" / "ui" / "components.py"
components_text = components.read_text(encoding="utf-8")
assert "def render_project_selector(" in components_text
assert "def collect_related_images(" in components_text
assert "def render_asset_gallery(" in components_text

# Import/data workflows belong to the service layer and must remain usable without Streamlit.
import_service = ROOT / "petrolab" / "services" / "import_service.py"
import_service_text = import_service.read_text(encoding="utf-8")
assert "import streamlit" not in import_service_text
assert "from streamlit" not in import_service_text
for function_name in [
    "def import_linked_sheets(",
    "def import_uploaded_sheets(",
    "def refresh_dataset_from_source(",
    "def inspect_linked_sheet(",
    "def inspect_uploaded_sheet(",
]:
    assert function_name in import_service_text

analysis_service = ROOT / "petrolab" / "services" / "analysis_service.py"
analysis_service_text = analysis_service.read_text(encoding="utf-8")
assert "import streamlit" not in analysis_service_text
assert "from streamlit" not in analysis_service_text
assert "def save_changes_to_database(" in analysis_service_text
assert "def save_changes_and_sync(" in analysis_service_text
assert "validate_sync_change" in analysis_service_text

image_service = ROOT / "petrolab" / "services" / "image_service.py"
image_service_text = image_service.read_text(encoding="utf-8")
assert "import streamlit" not in image_service_text
assert "from streamlit" not in image_service_text
assert "def create_image_assets(" in image_service_text
assert "def delete_image_asset(" in image_service_text
assert "def related_images_for_row(" in image_service_text

analysis_repository = ROOT / "petrolab" / "repositories" / "analysis_repository.py"
repository_text = analysis_repository.read_text(encoding="utf-8")
assert "import streamlit" not in repository_text
assert "from streamlit" not in repository_text
assert "def apply_analysis_changes(" in repository_text

image_repository = ROOT / "petrolab" / "repositories" / "image_repository.py"
image_repository_text = image_repository.read_text(encoding="utf-8")
assert "import streamlit" not in image_repository_text
assert "from streamlit" not in image_repository_text
assert "def create_image_record(" in image_repository_text
assert "def delete_image_record(" in image_repository_text

# Column normalization is a pure, reusable layer independent of UI and column order.
column_schema = ROOT / "petrolab" / "column_schema.py"
column_schema_text = column_schema.read_text(encoding="utf-8")
assert "import streamlit" not in column_schema_text
assert "from streamlit" not in column_schema_text
assert "def canonicalize_header(" in column_schema_text
assert "def apply_semantic_mapping(" in column_schema_text
assert "Group" in column_schema_text  # ambiguous Generation candidate is documented, not auto-renamed

# Streamlit 1.60 has removed the old width API from the supported path.
assert "use_container_width" not in app_text

# Intermediate guardrail: app.py must continue shrinking as pages are extracted.
app_lines = len(app_text.splitlines())
assert app_lines <= 325, f"app.py grew to {app_lines} lines; split pages/helpers before adding more UI"

# Empty exception handlers make scientific/data failures impossible to diagnose.
for path in [ROOT / "app.py", *sorted((ROOT / "petrolab").rglob("*.py"))]:
    text = path.read_text(encoding="utf-8")
    assert re.search(r"^\s*except\s*:\s*$", text, flags=re.MULTILINE) is None, f"bare except in {path}"

# Scientific domain and pure data helpers must stay independent of Streamlit.
pure_paths = [
    ROOT / "petrolab" / "column_schema.py",
    ROOT / "petrolab" / "dataframe_utils.py",
    ROOT / "petrolab" / "plot_presets.py",
    *sorted((ROOT / "petrolab" / "minerals").rglob("*.py")),
]
for path in pure_paths:
    text = path.read_text(encoding="utf-8")
    assert "import streamlit" not in text, f"Streamlit dependency leaked into {path}"
    assert "from streamlit" not in text, f"Streamlit dependency leaked into {path}"

assert (ROOT / "CONTRIBUTING.md").exists()
assert (ROOT / "ARCHITECTURE.md").exists()

print(f"architecture tests: OK; app.py = {app_lines} lines")
