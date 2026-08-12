from __future__ import annotations

from pathlib import Path


APP = Path("app.py")
text = APP.read_text(encoding="utf-8")

text = text.replace(
    "from pathlib import Path\n\nimport matplotlib.pyplot as plt",
    "from pathlib import Path\nfrom uuid import uuid4\n\nimport matplotlib.pyplot as plt",
    1,
)

text = text.replace("    META_COLUMNS,\n", "")
text = text.replace("    get_dataset,\n", "")
text = text.replace("    list_projects,\n", "")
text = text.replace("    update_analysis_values,\n", "")
text = text.replace("    compute_changes,\n", "")
text = text.replace("    display_value,\n", "")
text = text.replace("from petrolab.sources import sync_cell_changes\n", "")
text = text.replace(
    "from petrolab.ui.pages import render_home_page, render_projects_page, render_sources_page\n",
    "from petrolab.ui.components import collect_related_images, render_asset_gallery, render_project_selector\n"
    "from petrolab.ui.pages import render_analyses_page, render_home_page, render_projects_page, render_sources_page\n",
    1,
)

helpers_start = text.index('def project_selector(key: str = "project_select"):')
helpers_end = text.index("def style_df_from_groups(")
text = text[:helpers_start] + text[helpers_end:]

analyses_start = text.index('elif page == "Единая база":')
images_start = text.index('elif page == "Изображения":')
text = (
    text[:analyses_start]
    + 'elif page == "Единая база":\n    render_analyses_page()\n\n'
    + text[images_start:]
)

text = text.replace("project_selector(", "render_project_selector(")

assert 'elif page == "Единая база":\n    render_analyses_page()' in text
assert "def project_selector" not in text
assert "def collect_related_images" not in text
assert "def render_asset_gallery" not in text
assert "sync_cell_changes" not in text
assert "update_analysis_values" not in text
assert "compute_changes" not in text
assert "display_value" not in text
assert "from uuid import uuid4" in text
assert "render_project_selector(" in text

APP.write_text(text, encoding="utf-8")
print(f"Extracted unified analyses page; app.py = {len(text.splitlines())} lines")
