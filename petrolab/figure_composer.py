"""Raster publication composition for mixed PetroLab figure panels."""
from __future__ import annotations

from io import BytesIO
from typing import Mapping

from PIL import Image, ImageDraw, ImageFont, ImageOps

from petrolab.figure_recipes import LAYOUTS


def _font(size: int):
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size=size)
    except OSError:
        return ImageFont.load_default()


def _open_panel(raw: bytes) -> Image.Image:
    with Image.open(BytesIO(raw)) as image:
        normalized = ImageOps.exif_transpose(image)
        if normalized.mode == "RGBA":
            background = Image.new("RGB", normalized.size, "white")
            background.paste(normalized, mask=normalized.getchannel("A"))
            return background
        return normalized.convert("RGB").copy()


def compose_figure(
    *, layout_name: str, cells: list[dict], panels: Mapping[str, bytes], gap: int = 42, margin: int = 54,
) -> Image.Image:
    """Compose already-rendered XY/ternary/spider panels without distorting them."""
    if layout_name not in LAYOUTS:
        raise ValueError("Неизвестная сетка Figure Recipe")
    columns, rows = LAYOUTS[layout_name]
    expected = columns * rows
    if len(cells) != expected:
        raise ValueError("Количество ячеек не соответствует сетке")
    missing = [str(cell.get("position") or "?") for cell in cells if str(cell.get("position") or "") not in panels]
    if missing:
        raise ValueError("Загрузите панели: " + ", ".join(missing))

    opened = {position: _open_panel(raw) for position, raw in panels.items()}
    cell_width = max(image.width for image in opened.values())
    cell_height = max(image.height for image in opened.values())
    canvas = Image.new(
        "RGB",
        (margin * 2 + columns * cell_width + (columns - 1) * gap, margin * 2 + rows * cell_height + (rows - 1) * gap),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    label_font = _font(max(24, min(46, cell_width // 28)))
    for index, cell in enumerate(cells):
        position = str(cell["position"])
        image = opened[position]
        column, row = index % columns, index // columns
        left = margin + column * (cell_width + gap)
        top = margin + row * (cell_height + gap)
        x = left + (cell_width - image.width) // 2
        y = top + (cell_height - image.height) // 2
        canvas.paste(image, (x, y))
        caption = str(cell.get("caption") or position).strip()
        draw.text((left + 12, top + 10), caption, fill="#111827", font=label_font, stroke_width=2, stroke_fill="white")
    return canvas


def image_bytes(image: Image.Image, fmt: str) -> bytes:
    target = BytesIO()
    if fmt.lower() == "pdf":
        image.save(target, format="PDF", resolution=300.0)
    else:
        image.save(target, format="PNG", optimize=True)
    return target.getvalue()
