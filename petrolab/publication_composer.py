from __future__ import annotations

import io
import json
import math
from typing import Iterable

import matplotlib.pyplot as plt
from PIL import Image, ImageOps


LABEL_SEQUENCES = {
    "latin_upper": tuple("ABCDEFGHIJKLMNOPQRSTUVWXYZ"),
    "latin_lower": tuple("abcdefghijklmnopqrstuvwxyz"),
    "cyrillic_upper": tuple("АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"),
    "cyrillic_lower": tuple("абвгдежзийклмнопрстуфхцчшщъыьэюя"),
    "none": tuple(),
}

LABEL_MODE_TITLES = {
    "latin_upper": "A, B, C…",
    "latin_lower": "a, b, c…",
    "cyrillic_upper": "А, Б, В…",
    "cyrillic_lower": "а, б, в…",
    "none": "Без меток",
}


def panel_label_sequence(count: int, mode: str = "latin_upper") -> list[str]:
    """Return deterministic panel labels for the requested alphabet.

    Publication figures in PetroLab currently support up to 12 panels in the UI,
    but the helper deliberately handles longer sequences by continuing as A1/A2
    (or the equivalent last alphabet symbol + suffix) rather than silently
    dropping labels.
    """
    count = max(0, int(count))
    sequence = LABEL_SEQUENCES.get(str(mode))
    if sequence is None:
        raise ValueError(f"Неизвестный режим меток панелей: {mode}")
    if not sequence:
        return ["" for _ in range(count)]
    labels: list[str] = []
    for index in range(count):
        alphabet_index = index % len(sequence)
        cycle = index // len(sequence)
        base = sequence[alphabet_index]
        labels.append(base if cycle == 0 else f"{base}{cycle + 1}")
    return labels


def default_panel_label(
    text: str,
    *,
    enabled: bool = True,
    x: float = 0.025,
    y: float = 0.975,
    horizontal_alignment: str = "left",
    vertical_alignment: str = "top",
    font_size: float = 11.0,
    font_weight: str = "bold",
) -> dict:
    return {
        "text": str(text),
        "enabled": bool(enabled),
        "x": float(x),
        "y": float(y),
        "horizontal_alignment": str(horizontal_alignment),
        "vertical_alignment": str(vertical_alignment),
        "font_size": float(font_size),
        "font_weight": str(font_weight),
    }


def make_panel_labels(
    count: int,
    mode: str = "latin_upper",
    *,
    enabled: bool = True,
    font_size: float = 11.0,
) -> list[dict]:
    return [
        default_panel_label(text, enabled=enabled and bool(text), font_size=font_size)
        for text in panel_label_sequence(count, mode)
    ]


def _bounded_coordinate(value: object, fallback: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return fallback
    return max(-0.25, min(1.25, numeric))


def normalized_panel_label(label: dict | None, fallback_text: str = "") -> dict:
    raw = dict(label or {})
    text = str(raw.get("text", fallback_text))
    horizontal_alignment = str(raw.get("horizontal_alignment", "left"))
    if horizontal_alignment not in {"left", "center", "right"}:
        horizontal_alignment = "left"
    vertical_alignment = str(raw.get("vertical_alignment", "top"))
    if vertical_alignment not in {"top", "center", "bottom", "baseline"}:
        vertical_alignment = "top"
    font_weight = str(raw.get("font_weight", "bold"))
    if font_weight not in {"normal", "bold"}:
        font_weight = "bold"
    try:
        font_size = float(raw.get("font_size", 11.0))
    except (TypeError, ValueError):
        font_size = 11.0
    return {
        "text": text,
        "enabled": bool(raw.get("enabled", bool(text))),
        "x": _bounded_coordinate(raw.get("x", 0.025), 0.025),
        "y": _bounded_coordinate(raw.get("y", 0.975), 0.975),
        "horizontal_alignment": horizontal_alignment,
        "vertical_alignment": vertical_alignment,
        "font_size": max(4.0, min(72.0, font_size)),
        "font_weight": font_weight,
    }


def apply_panel_label(ax, label: dict | None, *, fallback_text: str = ""):
    cfg = normalized_panel_label(label, fallback_text=fallback_text)
    if not cfg["enabled"] or not cfg["text"]:
        return None
    return ax.text(
        cfg["x"],
        cfg["y"],
        cfg["text"],
        transform=ax.transAxes,
        ha=cfg["horizontal_alignment"],
        va=cfg["vertical_alignment"],
        fontsize=cfg["font_size"],
        fontweight=cfg["font_weight"],
        zorder=20,
    )


def _open_image(image_bytes: bytes) -> Image.Image:
    if not image_bytes:
        raise ValueError("Пустой источник изображения")
    with Image.open(io.BytesIO(image_bytes)) as image:
        corrected = ImageOps.exif_transpose(image)
        if corrected.mode not in {"RGB", "RGBA"}:
            corrected = corrected.convert("RGBA" if "A" in corrected.getbands() else "RGB")
        return corrected.copy()


def _panel_image(image_bytes: bytes, crop_mode: str, target_ratio: float | None = None) -> Image.Image:
    image = _open_image(image_bytes)
    if crop_mode == "cover" and target_ratio and target_ratio > 0:
        width, height = image.size
        current_ratio = width / height if height else target_ratio
        if abs(current_ratio - target_ratio) > 1e-6:
            if current_ratio > target_ratio:
                new_width = max(1, int(round(height * target_ratio)))
                left = max(0, (width - new_width) // 2)
                image = image.crop((left, 0, left + new_width, height))
            else:
                new_height = max(1, int(round(width / target_ratio)))
                top = max(0, (height - new_height) // 2)
                image = image.crop((0, top, width, top + new_height))
    return image


def build_publication_figure(
    panels: list[dict],
    *,
    columns: int = 2,
    width_in: float = 7.2,
    panel_height_in: float = 3.2,
    font_family: str = "Arial",
    background: str = "white",
    horizontal_space: float = 0.035,
    vertical_space: float = 0.045,
):
    """Compose raster panels into a deterministic Matplotlib publication figure.

    Every input panel occupies exactly one grid cell. Broken sources are rendered
    as an explicit error cell, so a decoding failure can never shift the labels or
    images of subsequent panels.
    """
    if not panels:
        raise ValueError("Нет панелей для сборки рисунка")
    ncols = max(1, min(int(columns), len(panels)))
    nrows = int(math.ceil(len(panels) / ncols))
    target_ratio = (float(width_in) / ncols) / max(0.1, float(panel_height_in))
    with plt.rc_context({"font.family": font_family}):
        figure, axes = plt.subplots(
            nrows,
            ncols,
            figsize=(float(width_in), float(panel_height_in) * nrows),
            squeeze=False,
            facecolor=background,
        )
        figure.subplots_adjust(
            left=0.0,
            right=1.0,
            bottom=0.0,
            top=1.0,
            wspace=max(0.0, float(horizontal_space)),
            hspace=max(0.0, float(vertical_space)),
        )
        for index, panel in enumerate(panels):
            ax = axes.flat[index]
            ax.set_facecolor(background)
            ax.set_xticks([])
            ax.set_yticks([])
            for spine in ax.spines.values():
                spine.set_visible(False)
            crop_mode = str(panel.get("crop_mode", "contain"))
            try:
                image = _panel_image(
                    bytes(panel.get("image_bytes") or b""),
                    crop_mode,
                    target_ratio=target_ratio,
                )
            except Exception as exc:
                ax.text(
                    0.5,
                    0.5,
                    f"Не удалось открыть панель\n{exc}",
                    transform=ax.transAxes,
                    ha="center",
                    va="center",
                    fontsize=8,
                    wrap=True,
                )
            else:
                ax.imshow(image, aspect="auto" if crop_mode == "cover" else "equal")
            apply_panel_label(ax, panel.get("label"))
            title = str(panel.get("title") or "").strip()
            if title:
                ax.set_title(title, fontsize=9, pad=3)

        for index in range(len(panels), nrows * ncols):
            axes.flat[index].axis("off")
        return figure


def figure_bytes(figure, format_name: str, dpi: int = 600) -> bytes:
    fmt = str(format_name).lower()
    if fmt not in {"png", "svg", "tiff", "tif"}:
        raise ValueError(f"Неподдерживаемый формат рисунка: {format_name}")
    buffer = io.BytesIO()
    save_format = "tiff" if fmt in {"tif", "tiff"} else fmt
    figure.savefig(
        buffer,
        format=save_format,
        dpi=int(dpi),
        facecolor=figure.get_facecolor(),
        bbox_inches=None,
        pad_inches=0,
    )
    return buffer.getvalue()


def publication_recipe(
    panels: Iterable[dict],
    *,
    columns: int,
    width_in: float,
    panel_height_in: float,
    font_family: str,
    journal_preset: str = "",
) -> dict:
    recipe_panels: list[dict] = []
    for index, panel in enumerate(panels):
        recipe_panels.append({
            "order": index,
            "source_id": panel.get("source_id"),
            "source_name": str(panel.get("source_name") or panel.get("title") or f"panel-{index + 1}"),
            "crop_mode": str(panel.get("crop_mode", "contain")),
            "title": str(panel.get("title") or ""),
            "label": normalized_panel_label(panel.get("label")),
        })
    return {
        "recipe_version": 1,
        "kind": "publication_composer",
        "journal_preset": str(journal_preset),
        "layout": {
            "columns": int(columns),
            "width_in": float(width_in),
            "panel_height_in": float(panel_height_in),
        },
        "font_family": str(font_family),
        "panels": recipe_panels,
    }


def recipe_json_bytes(recipe: dict) -> bytes:
    return json.dumps(recipe, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
