"""Canonical bridge between analytical Selection and thin-section spatial markers.

This module is intentionally UI-independent. It references the existing slide-marker,
analysis-row and physical-entity models; it does not create another point registry or
another Selection implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import hypot

from petrolab.db import connect
from petrolab.slides import ensure_slide_schema


_SQL_BATCH_SIZE = 400


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


def _analysis_batches(values: tuple[str, ...], size: int = _SQL_BATCH_SIZE) -> tuple[tuple[str, ...], ...]:
    if not values:
        return ()
    width = max(1, int(size))
    return tuple(values[start:start + width] for start in range(0, len(values), width))


def related_thin_section_markers(project_id: int, analysis_ids) -> tuple[PetrographyLink, ...]:
    """Return spatial markers explicitly linked to any exact selected ``analysis_id``.

    Each batch is one indexed SQL query, avoiding both N+1 marker scans and SQLite
    parameter-limit surprises for large linked-brushing selections. Physical identity is
    resolved only through ``slide_marker_analysis_links``; labels remain irrelevant.
    """
    wanted = _analysis_ids(analysis_ids)
    if not wanted:
        return ()
    ensure_slide_schema()
    grouped: dict[int, dict] = {}

    with connect() as con:
        for batch in _analysis_batches(wanted):
            placeholders = ",".join("?" for _ in batch)
            sql = f"""
                SELECT
                    m.id AS marker_id,
                    m.slide_image_id AS slide_image_id,
                    i.thin_section_id AS thin_section_id,
                    section.name AS thin_section_name,
                    i.title AS image_title,
                    i.image_type AS image_type,
                    COALESCE(NULLIF(m.label, ''), entity.name, '') AS marker_label,
                    m.x_norm AS x_norm,
                    m.y_norm AS y_norm,
                    all_links.analysis_id AS linked_analysis_id
                FROM slide_markers m
                JOIN slide_images i
                  ON i.id=m.slide_image_id AND i.project_id=m.project_id
                JOIN physical_entities section
                  ON section.id=i.thin_section_id
                 AND section.project_id=m.project_id
                 AND section.kind='thin_section'
                LEFT JOIN physical_entities entity ON entity.id=m.entity_id
                JOIN slide_marker_analysis_links all_links ON all_links.marker_id=m.id
                WHERE m.project_id=?
                  AND EXISTS (
                      SELECT 1
                      FROM slide_marker_analysis_links selected_link
                      WHERE selected_link.marker_id=m.id
                        AND selected_link.analysis_id IN ({placeholders})
                  )
                ORDER BY
                    section.name COLLATE NOCASE,
                    i.image_type COLLATE NOCASE,
                    i.title COLLATE NOCASE,
                    marker_label COLLATE NOCASE,
                    m.id,
                    all_links.analysis_id
            """
            rows = con.execute(sql, (int(project_id), *batch)).fetchall()
            for row in rows:
                marker_id = int(row["marker_id"])
                item = grouped.setdefault(
                    marker_id,
                    {
                        "marker_id": marker_id,
                        "slide_image_id": int(row["slide_image_id"]),
                        "thin_section_id": int(row["thin_section_id"]),
                        "thin_section_name": str(row["thin_section_name"]),
                        "image_title": str(row["image_title"]),
                        "image_type": str(row["image_type"]),
                        "marker_label": str(row["marker_label"] or ""),
                        "x_norm": float(row["x_norm"]),
                        "y_norm": float(row["y_norm"]),
                        "analysis_ids": [],
                    },
                )
                analysis_id = str(row["linked_analysis_id"]).strip()
                if analysis_id and analysis_id not in item["analysis_ids"]:
                    item["analysis_ids"].append(analysis_id)

    links = [
        PetrographyLink(
            marker_id=item["marker_id"],
            slide_image_id=item["slide_image_id"],
            thin_section_id=item["thin_section_id"],
            thin_section_name=item["thin_section_name"],
            image_title=item["image_title"],
            image_type=item["image_type"],
            marker_label=item["marker_label"],
            x_norm=item["x_norm"],
            y_norm=item["y_norm"],
            analysis_ids=tuple(item["analysis_ids"]),
        )
        for item in grouped.values()
    ]
    return tuple(
        sorted(
            links,
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
    wanted = _analysis_ids(analysis_ids)
    if not wanted:
        return ()
    dataset_ids: set[int] = set()
    with connect() as con:
        for batch in _analysis_batches(wanted):
            placeholders = ",".join("?" for _ in batch)
            rows = con.execute(
                f"""SELECT DISTINCT a.dataset_id
                    FROM analysis_rows a
                    JOIN project_dataset_links p ON p.dataset_id=a.dataset_id
                    WHERE p.project_id=? AND a.analysis_id IN ({placeholders})
                    ORDER BY a.dataset_id""",
                (int(project_id), *batch),
            ).fetchall()
            dataset_ids.update(int(row["dataset_id"]) for row in rows)
    return tuple(sorted(dataset_ids))


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
    very wide or tall images. The threshold is relative to image width, not master pixel
    count, and therefore remains usable for large microscope scans.
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
