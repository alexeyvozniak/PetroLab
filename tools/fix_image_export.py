from pathlib import Path

path = Path("app.py")
text = path.read_text(encoding="utf-8")
anchor = "from petrolab.plotting import MARKERS, build_scatter, figure_png_bytes, figure_svg_bytes\n"
assert anchor in text
if "from petrolab.services.image_service import list_all_images\n" not in text:
    text = text.replace(anchor, anchor + "from petrolab.services.image_service import list_all_images\n")
assert "list_image_assets()" in text
text = text.replace("list_image_assets()", "list_all_images()")
path.write_text(text, encoding="utf-8")
print("Image export routed through service")
