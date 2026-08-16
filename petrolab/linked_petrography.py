"""Canonical bridge between analytical Selection and thin-section spatial markers.

This module is intentionally UI-independent.  It references the existing slide marker,
analysis-row and physical-entity models; it does not create another point registry or
another Selection implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from petrolab.db import connect
from petrolab.measurement_registry import list_entities
from petrolab.slides import list_slide_images, list_slide_markers


@dataclass(frozen=True)
class PetrographyLink:
    marker_id: int
    slide_image_id: int
    thin_section_id: int
    thin_section_name: str
    image_title: str
    image_type: str
    marker_label: str
    x_norm: float
    y_norm: float
    analysis_ids: tuple[str, ...]

    @property
    def display_label(self) -> str:
        marker = self.marker_label or f"Точка {self.marker_id}"
        return f"{self.thin_section_name} · {self.image_title} · {marker}"


def _analysis_ids(values) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))


def related_thin_section_markers(project_id: int, analysis_ids) -> tuple[PetrographyLink, ...]:
    """Return exact spatial markers whose stored links intersect ``analysis_ids``.

    Physical identity is resolved only through ``slide_marker_analysis_links``.  Labels,
    Sample names and Point strings are never used to infer a relationship.
    """
    wanted = set(_analysis_ids(analysis_ids))
    if not wanted:
        return ()

    images = {int(image.id): image for image in list_slide_images(int(project_id))}
    sections = {
        int(entity["id"]): str(entity.get("name") or f"Шлиф {entity['id']}")
        for entity in list_entities(int(project_id))
        if str(entity.get("kind") or "") == "thin_section"
    }
    result: list[PetrographyLink] = []
    for marker in list_slide_markers(int(project_id)):
        linked = _analysis_ids(marker.get("analysis_ids", ()))
        if not wanted.intersection(linked):
            continue
        image = images.get(int(marker["slide_image_id"]))
        if image is None or image.thin_section_id is None:
            continue
        section_id = int(image.thin_section_id)
        if section_id not in sections:
            continue
        result.append(
            PetrographyLink(
                marker_id=int(marker["id"]),
                slide_image_id=int(image.id),
                thin_section_id=section_id,
                thin_section_name=sections[section_id],
                image_title=str(image.title),
                image_type=str(image.image_type),
                marker_label=str(marker.get("label") or marker.get("entity_name") or ""),
                x_norm=float(marker["x_norm"]),
                y_norm=float(marker["y_norm"]),
                analysis_ids=linked,
            )
        )
    return tuple(
        sorted(
            result,
            key=lambda item: (
                item.thin_section_name.casefold(),
                item.image_type.casefold(),
                item.image_title.casefold(),
                item.marker_label.casefold(),
                item.marker_id,
            ),
        )
    )


def marker_ids_for_selection(markers: list[dict], analysis_ids) -> tuple[int, ...]:
    """Return marker ids on the current image that intersect canonical Selection."""
    wanted = set(_analysis_ids(analysis_ids))
    if not wanted:
        return ()
    return tuple(
        int(marker["id"])
        for marker in markers
        if wanted.intersection(_analysis_ids(marker.get("analysis_ids", ())))
    )


def analysis_ids_for_marker(markers: list[dict], marker_id: int) -> tuple[str, ...]:
    """Resolve all measurements explicitly linked to one physical image marker."""
    target = int(marker_id)
    for marker in markers:
        if int(marker["id"]) == target:
            return _analysis_ids(marker.get("analysis_ids", ()))
    return ()


def dataset_ids_for_analysis_ids(project_id: int, analysis_ids) -> tuple[int, ...]:
    """Resolve datasets for an exact analysis scope without changing that scope."""
    wanted = set(_analysis_ids(analysis_ids))
    if not wanted:
        return ()
    with connect() as con:
        rows = con.execute(
            """SELECT a.analysis_id, a.dataset_id
               FROM analysis_rows a
               JOIN project_dataset_links p ON p.dataset_id=a.dataset_id
               WHERE p.project_id=?
               ORDER BY a.dataset_id, a.analysis_id""",
            (int(project_id),),
        ).fetchall()
    return tuple(
        dict.fromkeys(
            int(row["dataset_id"])
            for row in rows
            if str(row["analysis_id"]) in wanted
        )
    )


def nearest_marker_id(
    markers: list[dict],
    *,
    x_norm: float,
    y_norm: float,
    aspect_ratio: float = 1.0,
    max_distance: float = 0.035,
) -> int | None:
    """Find a marker close to a click in normalized coordinates.

    ``aspect_ratio`` is image height / width, so distance remains visually sensible on
    very wide or tall images.  The threshold is relative to image width, not master
    pixel count, and therefore remains usable for large microscope scans.
    """
    ratio = max(float(aspect_ratio), 1e-9)
    best_id: int | None = None
    best_distance = float("inf")
    for marker in markers:
        dx = float(marker["x_norm"]) - float(x_norm)
        dy = (float(marker["y_norm"]) - float(y_norm)) * ratio
        distance = hypot(dx, dy)
        if distance < best_distance:
            best_distance = distance
            best_id = int(marker["id"])
    return best_id if best_id is not None and best_distance <= float(max_distance) else None
