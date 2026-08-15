"""v0.15.1 safety rules for slide markers and composite physical points.

A label is presentation metadata, not physical identity. Two markers named P-1
on different images remain different physical points unless the user explicitly
links them to the same entity. Composite metadata is restored from the physical
registry after analytical values are merged so chemistry can never overwrite the
Sample/thin-section identity of a target.
"""
from __future__ import annotations

import pandas as pd

from petrolab.db import connect


_AUTO_POINT_DESCRIPTION = "Создано из разметки шлифа для composite analysis"
_LINK_SOURCE_AUTO = "auto_marker"
_LINK_SOURCE_EXPLICIT = "explicit"
_LINK_SOURCE_LEGACY_AMBIGUOUS = "legacy_ambiguous"


def _ensure_marker_link_source_schema() -> None:
    from petrolab.slides import ensure_slide_schema

    ensure_slide_schema()
    with connect() as con:
        columns = {str(row[1]) for row in con.execute("PRAGMA table_info(slide_markers)").fetchall()}
        if "entity_link_source" not in columns:
            con.execute(
                "ALTER TABLE slide_markers ADD COLUMN entity_link_source TEXT NOT NULL DEFAULT ''"
            )
            con.commit()


def _validate_marker_entity(con, project_id: int, slide_image_id: int, entity_id: int) -> None:
    image = con.execute(
        "SELECT project_id,thin_section_id FROM slide_images WHERE id=?", (int(slide_image_id),)
    ).fetchone()
    if not image or int(image["project_id"]) != int(project_id):
        raise ValueError("Изображение не относится к этому проекту")
    if image["thin_section_id"] is None:
        raise ValueError("Сначала привяжите изображение к шлифу")
    entity = con.execute(
        "SELECT project_id,parent_id,kind FROM physical_entities WHERE id=?", (int(entity_id),)
    ).fetchone()
    if not entity or int(entity["project_id"]) != int(project_id):
        raise ValueError("Физическая точка не относится к этому проекту")
    if str(entity["kind"]) not in {"probe_point", "la_crater"}:
        raise ValueError("Маркер можно связать только с аналитической физической точкой")
    if entity["parent_id"] is None or int(entity["parent_id"]) != int(image["thin_section_id"]):
        raise ValueError("Физическая точка относится к другому шлифу")


def _unique_marker_entity_name(project_id: int, thin_section_id: int, marker: dict) -> str:
    base = str(marker.get("label") or marker.get("entity_name") or "").strip()
    if not base:
        base = f"P-{int(marker['id'])}"
    with connect() as con:
        exists = con.execute(
            """SELECT 1 FROM physical_entities
               WHERE project_id=? AND parent_id=? AND kind='probe_point' AND name=?""",
            (int(project_id), int(thin_section_id), base),
        ).fetchone()
        if not exists:
            return base
        candidate = f"{base} · marker {int(marker['id'])}"
        if not con.execute(
            """SELECT 1 FROM physical_entities
               WHERE project_id=? AND parent_id=? AND kind='probe_point' AND name=?""",
            (int(project_id), int(thin_section_id), candidate),
        ).fetchone():
            return candidate
        return f"{candidate} · image {int(marker['slide_image_id'])}"


def _mark_legacy_ambiguous_links(project_id: int) -> None:
    """Quarantine old implicit many-markers-to-one-point merges instead of guessing a split."""
    _ensure_marker_link_source_schema()
    with connect() as con:
        rows = con.execute(
            """SELECT m.entity_id, COUNT(*) AS marker_count
               FROM slide_markers m
               JOIN physical_entities e ON e.id=m.entity_id
               WHERE m.project_id=? AND m.entity_id IS NOT NULL
                 AND COALESCE(m.entity_link_source,'')=''
                 AND e.description=?
               GROUP BY m.entity_id HAVING COUNT(*) > 1""",
            (int(project_id), _AUTO_POINT_DESCRIPTION),
        ).fetchall()
        ambiguous_ids = [int(row["entity_id"]) for row in rows]
        if ambiguous_ids:
            marks = ",".join("?" for _ in ambiguous_ids)
            con.execute(
                f"""UPDATE slide_markers SET entity_link_source=?
                    WHERE project_id=? AND entity_id IN ({marks})
                      AND COALESCE(entity_link_source,'')=''""",
                [_LINK_SOURCE_LEGACY_AMBIGUOUS, int(project_id), *ambiguous_ids],
            )
        con.commit()


def ambiguous_marker_entity_ids(project_id: int) -> set[int]:
    _mark_legacy_ambiguous_links(int(project_id))
    with connect() as con:
        rows = con.execute(
            """SELECT DISTINCT entity_id FROM slide_markers
               WHERE project_id=? AND entity_id IS NOT NULL AND entity_link_source=?""",
            (int(project_id), _LINK_SOURCE_LEGACY_AMBIGUOUS),
        ).fetchall()
    return {int(row["entity_id"]) for row in rows}


def _remove_moved_marker_analysis_links(
    project_id: int,
    old_entity_id: int,
    moved_analysis_ids: list[str],
) -> None:
    """Delete only links belonging exclusively to the marker that moved.

    Existing links keep their original ``link_role``, ``note`` and ``created_at``.
    If another marker that still belongs to the old entity references the same
    analysis, that analysis remains linked there as well.
    """
    if not moved_analysis_ids:
        return
    with connect() as con:
        remaining_marker_rows = con.execute(
            """SELECT DISTINCT ml.analysis_id
               FROM slide_markers m
               JOIN slide_marker_analysis_links ml ON ml.marker_id=m.id
               WHERE m.project_id=? AND m.entity_id=?""",
            (int(project_id), int(old_entity_id)),
        ).fetchall()
        remaining_marker_ids = {str(row["analysis_id"]) for row in remaining_marker_rows}
        removable = {
            str(value) for value in moved_analysis_ids if str(value) not in remaining_marker_ids
        }
        if not removable:
            return
        con.executemany(
            "DELETE FROM physical_point_analysis_links WHERE entity_id=? AND analysis_id=?",
            [(int(old_entity_id), analysis_id) for analysis_id in sorted(removable)],
        )
        con.commit()


def set_slide_marker_entity(project_id: int, marker_id: int, entity_id: int) -> None:
    """Explicitly declare that one image marker represents an existing physical point."""
    _ensure_marker_link_source_schema()
    from petrolab.composite_points import add_physical_point_links, ensure_composite_schema

    ensure_composite_schema()
    with connect() as con:
        marker = con.execute(
            "SELECT project_id,slide_image_id,entity_id,entity_link_source FROM slide_markers WHERE id=?",
            (int(marker_id),),
        ).fetchone()
        if not marker or int(marker["project_id"]) != int(project_id):
            raise ValueError("Маркер не относится к этому проекту")
        old_entity_id = int(marker["entity_id"]) if marker["entity_id"] is not None else None
        _validate_marker_entity(con, int(project_id), int(marker["slide_image_id"]), int(entity_id))
        links = con.execute(
            "SELECT analysis_id FROM slide_marker_analysis_links WHERE marker_id=? ORDER BY analysis_id",
            (int(marker_id),),
        ).fetchall()
        analysis_ids = [str(row["analysis_id"]) for row in links]
        con.execute(
            "UPDATE slide_markers SET entity_id=?, entity_link_source=? WHERE id=?",
            (int(entity_id), _LINK_SOURCE_EXPLICIT, int(marker_id)),
        )
        con.commit()

    if old_entity_id is not None and old_entity_id != int(entity_id):
        _remove_moved_marker_analysis_links(
            int(project_id), int(old_entity_id), analysis_ids
        )
    if analysis_ids:
        add_physical_point_links(
            int(project_id), int(entity_id), analysis_ids,
            link_role="explicit_slide_marker", note=f"Явная связь маркера {int(marker_id)}",
        )


def install() -> None:
    import petrolab.composite_points as composite
    import petrolab.slides as slides

    if getattr(composite, "_v0151_physical_point_safety_installed", False):
        return

    original_create_slide_marker = slides.create_slide_marker
    original_sync = composite.sync_slide_markers_to_physical_points
    original_composite_dataframe = composite.composite_points_dataframe

    def create_slide_marker_safe(
        project_id: int, *, slide_image_id: int, x_norm: float, y_norm: float,
        label: str = "", note: str = "", field_id: int | None = None,
        entity_id: int | None = None, analysis_ids: tuple[str, ...] = (),
    ) -> int:
        if entity_id is not None:
            # Tests/recovery may switch the active database after package import.
            # Ensure the additive provenance column in the current database lazily.
            _ensure_marker_link_source_schema()
            with connect() as con:
                _validate_marker_entity(con, int(project_id), int(slide_image_id), int(entity_id))
        marker_id = original_create_slide_marker(
            int(project_id), slide_image_id=int(slide_image_id), x_norm=float(x_norm),
            y_norm=float(y_norm), label=label, note=note, field_id=field_id,
            entity_id=entity_id, analysis_ids=analysis_ids,
        )
        if entity_id is not None:
            with connect() as con:
                con.execute(
                    "UPDATE slide_markers SET entity_link_source=? WHERE id=?",
                    (_LINK_SOURCE_EXPLICIT, int(marker_id)),
                )
                con.commit()
        return int(marker_id)

    def find_or_create_marker_entity_safe(
        project_id: int, marker: dict, thin_section_id: int, sample_id: int | None,
    ) -> int | None:
        from petrolab.measurement_registry import create_entity

        existing_entity = marker.get("entity_id")
        if existing_entity is not None:
            with connect() as con:
                _validate_marker_entity(
                    con, int(project_id), int(marker["slide_image_id"]), int(existing_entity)
                )
            return int(existing_entity)
        name = _unique_marker_entity_name(int(project_id), int(thin_section_id), marker)
        return create_entity(
            int(project_id), kind="probe_point", name=name,
            sample_id=sample_id, parent_id=int(thin_section_id),
            description=_AUTO_POINT_DESCRIPTION,
        )

    def sync_slide_markers_safe(project_id: int) -> int:
        _mark_legacy_ambiguous_links(int(project_id))
        changed = int(original_sync(int(project_id)))
        with connect() as con:
            con.execute(
                """UPDATE slide_markers SET entity_link_source=?
                   WHERE project_id=? AND entity_id IS NOT NULL
                     AND COALESCE(entity_link_source,'')=''""",
                (_LINK_SOURCE_AUTO, int(project_id)),
            )
            con.commit()
        return changed

    def composite_dataframe_safe(project_id: int, *, thin_section_id: int | None = None) -> pd.DataFrame:
        frame = original_composite_dataframe(int(project_id), thin_section_id=thin_section_id)
        if frame.empty or "_physical_point_id" not in frame.columns:
            return frame
        ambiguous = ambiguous_marker_entity_ids(int(project_id))
        if ambiguous:
            frame = frame.loc[
                ~pd.to_numeric(frame["_physical_point_id"], errors="coerce").isin(ambiguous)
            ].copy()
        if frame.empty:
            return frame
        ids = [int(value) for value in pd.to_numeric(
            frame["_physical_point_id"], errors="coerce"
        ).dropna().unique().tolist()]
        if not ids:
            return frame
        marks = ",".join("?" for _ in ids)
        with connect() as con:
            rows = con.execute(
                f"""SELECT e.id,e.name,s.name AS sample_name,p.name AS thin_section_name
                    FROM physical_entities e
                    LEFT JOIN samples s ON s.id=e.sample_id
                    LEFT JOIN physical_entities p ON p.id=e.parent_id
                    WHERE e.id IN ({marks})""",
                ids,
            ).fetchall()
        metadata = {int(row["id"]): dict(row) for row in rows}
        for index in frame.index:
            point_id = int(frame.at[index, "_physical_point_id"])
            item = metadata.get(point_id)
            if not item:
                continue
            frame.at[index, "Physical Point"] = str(item.get("name") or "")
            frame.at[index, "Sample"] = str(item.get("sample_name") or "")
            frame.at[index, "Thin Section"] = str(item.get("thin_section_name") or "")
        return frame

    slides.create_slide_marker = create_slide_marker_safe
    composite._find_or_create_marker_entity = find_or_create_marker_entity_safe
    composite.sync_slide_markers_to_physical_points = sync_slide_markers_safe
    composite.composite_points_dataframe = composite_dataframe_safe
    composite._v0151_physical_point_safety_installed = True
