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
    """Return deterministic panel labels for the requested alphabet."""
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


def _finite_float(value: object, fallback: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return float(fallback)
    return numeric if math.isfinite(numeric) else float(fallback)


def _safe_bool(value: object, fallback: bool) -> bool:
    if value is None:
        return bool(fallback)
    try:
        return bool(value)
    except (TypeError, ValueError):
        return bool(fallback)


def _bounded_coordinate(value: object, fallback: float) -> float:
    numeric = _finite_float(value, fallback)
    return max(-0.25, min(1.25, numeric))


def normalized_panel_label(label: dict | None, fallback_text: str = "") -> dict:
    raw = dict(label or {})
    text_value = raw.get("text", fallback_text)
    text = fallback_text if text_value is None else str(text_value)
    horizontal_alignment = str(raw.get("horizontal_alignment", "left"))
    if horizontal_alignment not in {"left", "center", "right"}:
        horizontal_alignment = "left"
    vertical_alignment = str(raw.get("vertical_alignment", "top"))
    if vertical_alignment not in {"top", "center", "bottom", "baseline"}:
        vertical_alignment = "top"
    font_weight = str(raw.get("font_weight", "bold"))
    if font_weight not in {"normal", "bold"}:
        font_weight = "bold"
    font_size = _finite_float(raw.get("font_size", 11.0), 11.0)
    return {
        "text": text,
        "enabled": _safe_bool(raw.get("enabled", bool(text)), bool(text)),
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


def normalized_publication_recipe(payload: object) -> dict:
    """Validate and normalize a v1 composer recipe before UI state is restored."""
    if not isinstance(payload, dict):
        raise ValueError("Recipe должен быть JSON-объектом")
    if str(payload.get("kind") or "") != "publication_composer":
        raise ValueError("Это не recipe редактора мультипанельных рисунков")
    try:
        version = int(payload.get("recipe_version", 0))
    except (TypeError, ValueError):
        version = 0
    if version != 1:
        raise ValueError(f"Неподдерживаемая версия recipe: {version}")
    raw_panels = payload.get("panels")
    if not isinstance(raw_panels, list) or not raw_panels:
        raise ValueError("Recipe не содержит панелей")
    if len(raw_panels) > 12:
        raise ValueError("Recipe содержит больше 12 панелей")
    panels: list[dict] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_panels):
        if not isinstance(raw, dict):
            raise ValueError(f"Панель {index + 1} в recipe повреждена")
        source_id = str(raw.get("source_id") or "").strip()
        if not source_id:
            raise ValueError(f"У панели {index + 1} отсутствует source_id")
        if source_id in seen_ids:
            raise ValueError(f"Recipe содержит повторяющийся source_id: {source_id}")
        seen_ids.add(source_id)
        crop_mode = str(raw.get("crop_mode") or "contain")
        if crop_mode not in {"contain", "cover"}:
            crop_mode = "contain"
        panels.append({
            "order": index,
            "source_id": source_id,
            "source_name": str(raw.get("source_name") or source_id),
            "crop_mode": crop_mode,
            "title": str(raw.get("title") or ""),
            "label": normalized_panel_label(raw.get("label")),
        })
    layout = payload.get("layout") if isinstance(payload.get("layout"), dict) else {}
    columns = int(max(1, min(4, round(_finite_float(layout.get("columns", 2), 2.0)))))
    width_in = max(2.0, min(20.0, _finite_float(layout.get("width_in", 7.2), 7.2)))
    panel_height_in = max(1.0, min(10.0, _finite_float(layout.get("panel_height_in", 3.2), 3.2)))
    return {
        "recipe_version": 1,
        "kind": "publication_composer",
        "journal_preset": str(payload.get("journal_preset") or ""),
        "layout": {
            "columns": columns,
            "width_in": width_in,
            "panel_height_in": panel_height_in,
        },
        "font_family": str(payload.get("font_family") or "Arial"),
        "panels": panels,
    }


def parse_publication_recipe_bytes(content: bytes) -> dict:
    if not content:
        raise ValueError("Recipe-файл пуст")
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Recipe-файл не является корректным UTF-8 JSON") from exc
    return normalized_publication_recipe(payload)


def recipe_json_bytes(recipe: dict) -> bytes:
    return json.dumps(recipe, ensure_ascii=False, indent=2, sort_keys=True).encode("utf-8")
