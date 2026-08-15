from __future__ import annotations

import io
import json

import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image

from petrolab.multi_panel_plotting import build_multi_panel_scatter
from petrolab.publication_composer import (
    build_publication_figure,
    default_panel_label,
    figure_bytes,
    panel_label_sequence,
    publication_recipe,
    recipe_json_bytes,
)


def _png_bytes(value: int) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (64, 40), (value, value, value)).save(buffer, format="PNG")
    return buffer.getvalue()


def _panel(index: int, label: dict) -> dict:
    return {
        "source_id": f"test:{index}",
        "source_name": f"panel-{index}.png",
        "image_bytes": _png_bytes(30 + index * 20),
        "crop_mode": "contain",
        "label": label,
    }


def _visible_axis_texts(figure) -> list[str]:
    values: list[str] = []
    for axis in figure.axes:
        if not axis.axison:
            continue
        values.extend(text.get_text() for text in axis.texts if text.get_visible())
    return values


def main() -> None:
    assert panel_label_sequence(6, "latin_upper") == ["A", "B", "C", "D", "E", "F"]
    assert panel_label_sequence(6, "cyrillic_upper") == ["А", "Б", "В", "Г", "Д", "Е"]
    assert panel_label_sequence(4, "latin_lower") == ["a", "b", "c", "d"]
    assert panel_label_sequence(3, "none") == ["", "", ""]

    labels = [default_panel_label(text) for text in panel_label_sequence(6, "latin_upper")]
    figure = build_publication_figure([_panel(index, label) for index, label in enumerate(labels)], columns=3)
    texts = _visible_axis_texts(figure)
    for label in ["A", "B", "C", "D", "E", "F"]:
        assert texts.count(label) == 1
    assert len(figure.axes) == 6
    assert len(figure_bytes(figure, "png", 300)) > 1000
    assert b"<svg" in figure_bytes(figure, "svg", 300)[:1000]
    assert len(figure_bytes(figure, "tiff", 300)) > 1000
    plt.close(figure)

    custom = [default_panel_label(text) for text in panel_label_sequence(5, "latin_upper")]
    custom[1]["enabled"] = False
    custom[2]["text"] = "C*"
    custom[3]["x"] = 0.81
    custom[3]["y"] = 0.11
    figure = build_publication_figure([_panel(index, label) for index, label in enumerate(custom)], columns=3)
    texts = _visible_axis_texts(figure)
    assert "A" in texts
    assert "B" not in texts
    assert "C*" in texts
    assert "D" in texts and "E" in texts
    assert len(figure.axes) == 6, "5 panels in 2x3 must keep one stable blank cell"
    assert not figure.axes[-1].axison, "unused grid cell must be blank"
    d_text = next(text for text in figure.axes[3].texts if text.get_text() == "D")
    assert abs(float(d_text.get_position()[0]) - 0.81) < 1e-9
    assert abs(float(d_text.get_position()[1]) - 0.11) < 1e-9

    recipe = publication_recipe(
        [_panel(index, label) for index, label in enumerate(custom)],
        columns=3,
        width_in=7.2,
        panel_height_in=3.2,
        font_family="Arial",
        journal_preset="Lithos",
    )
    payload = json.loads(recipe_json_bytes(recipe).decode("utf-8"))
    assert payload["kind"] == "publication_composer"
    assert payload["journal_preset"] == "Lithos"
    assert payload["panels"][1]["label"]["enabled"] is False
    assert payload["panels"][2]["label"]["text"] == "C*"
    assert abs(float(payload["panels"][3]["label"]["x"]) - 0.81) < 1e-9
    plt.close(figure)

    broken = _panel(0, default_panel_label("A"))
    broken["image_bytes"] = b"not-an-image"
    second = _panel(1, default_panel_label("B"))
    figure = build_publication_figure([broken, second], columns=2)
    assert any("Не удалось открыть панель" in text.get_text() for text in figure.axes[0].texts)
    assert any(text.get_text() == "A" for text in figure.axes[0].texts)
    assert any(text.get_text() == "B" for text in figure.axes[1].texts)
    plt.close(figure)

    scientific = pd.DataFrame({
        "X": [1.0, 2.0, 3.0],
        "Y": [2.0, 3.0, 4.0],
        "Z": [4.0, 5.0, 6.0],
    })
    scientific_figure = build_multi_panel_scatter(
        scientific,
        [
            {"x": "X", "y": "Y", "title": "", "panel_label": default_panel_label("А")},
            {
                "x": "X",
                "y": "Z",
                "title": "",
                "panel_label": default_panel_label("Б", x=0.82, y=0.14),
            },
        ],
        columns=2,
        show_legend=False,
    )
    assert any(text.get_text() == "А" for text in scientific_figure.axes[0].texts)
    b_text = next(text for text in scientific_figure.axes[1].texts if text.get_text() == "Б")
    assert abs(float(b_text.get_position()[0]) - 0.82) < 1e-9
    assert abs(float(b_text.get_position()[1]) - 0.14) < 1e-9
    plt.close(scientific_figure)

    print("publication composer tests: OK")


if __name__ == "__main__":
    main()
