from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")

start = text.index('elif page == "Изображения":')
end = text.index('elif page == "Пересчёт формул":')
text = text[:start] + 'elif page == "Изображения":\n    render_images_page()\n\n' + text[end:]

text = text.replace("from pathlib import Path\n", "")
text = text.replace("from uuid import uuid4\n", "")
text = text.replace("    ASSETS_DIR,\n", "")
text = text.replace("    add_image_asset,\n", "")
text = text.replace("    delete_image_asset,\n", "")
text = text.replace("    list_image_assets,\n", "")
text = text.replace(
    "from petrolab.ui.components import collect_related_images, render_asset_gallery, render_project_selector\n",
    "from petrolab.ui.components import collect_related_images, render_asset_gallery, render_project_selector\n",
)
old_pages = "from petrolab.ui.pages import render_analyses_page, render_home_page, render_projects_page, render_sources_page\n"
new_pages = "from petrolab.ui.pages import render_analyses_page, render_home_page, render_images_page, render_projects_page, render_sources_page\n"
assert old_pages in text
text = text.replace(old_pages, new_pages)

assert 'render_images_page()' in text
assert 'asset_dir = ASSETS_DIR' not in text
assert 'uuid4()' not in text
assert 'add_image_asset(' not in text
assert 'delete_image_asset(' not in text

path.write_text(text, encoding="utf-8")
print(f"Extracted images page; app.py = {len(text.splitlines())} lines")
