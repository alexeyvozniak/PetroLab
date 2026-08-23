from __future__ import annotations

from io import BytesIO

from PIL import Image

from petrolab.figure_composer import compose_figure, image_bytes


def panel(color: str, size: tuple[int, int]) -> bytes:
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


cells = [
    {"position": "A", "caption": "A", "type": "XY", "reference": "xy"},
    {"position": "B", "caption": "B", "type": "REE / Spider", "reference": "spider"},
]
result = compose_figure(layout_name="2 × 1", cells=cells, panels={"A": panel("red", (300, 180)), "B": panel("blue", (240, 220))})
assert result.width > 600 and result.height >= 320
assert len(image_bytes(result, "png")) > 100
assert len(image_bytes(result, "pdf")) > 100
try:
    compose_figure(layout_name="2 × 1", cells=cells, panels={"A": panel("red", (100, 100))})
except ValueError as exc:
    assert "B" in str(exc)
else:
    raise AssertionError("missing panel was accepted")
print("figure composer tests: OK")
