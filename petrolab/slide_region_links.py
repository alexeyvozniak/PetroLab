"""Explicit links between a mapped thin-section region and detailed images.

This is intentionally a semantic/spatial link, not an automatic image registration.
PetroLab may know that an EDS/BSE image belongs to a selected region without
pretending that pixel coordinates are already co-registered.
"""
from __future__ import annotations

from petrolab.db import connect
from petrolab.slides import ensure_slide_schema


def _columns(con, table: str) -> set[str]:
    return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def ensure_region_image_schema() -> None:
    ensure_slide_schema()
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS slide_field_image_links (
                project_id INTEGER NOT NULL,
                field_id INTEGER NOT NULL,
                image_id INTEGER NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(field_id, image_id),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(field_id) REFERENCES slide_fields(id) ON DELETE CASCADE,
                FOREIGN KEY(image_id) REFERENCES slide_images(id) ON DELETE CASCADE
            )"""
        )
        # Development builds briefly created this table without project_id. Migrate those
        # databases in place and derive ownership only from the already project-scoped field.
        if "project_id" not in _columns(con, "slide_field_image_links"):
            con.execute("ALTER TABLE slide_field_image_links ADD COLUMN project_id INTEGER")
            con.execute(
                """UPDATE slide_field_image_links
                   SET project_id=(SELECT project_id FROM slide_fields WHERE slide_fields.id=slide_field_image_links.field_id)
                   WHERE project_id IS NULL"""
            )
        con.execute("CREATE INDEX IF NOT EXISTS idx_field_image_project ON slide_field_image_links(project_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_field_image_image ON slide_field_image_links(image_id)")
        con.commit()


def set_field_image_links(project_id: int, field_id: int, image_ids: list[int] | tuple[int, ...], *, note: str = "") -> None:
    ensure_region_image_schema()
    ids = tuple(dict.fromkeys(int(value) for value in image_ids))
    with connect() as con:
        field = con.execute(
            """SELECT f.project_id, si.thin_section_id
               FROM slide_fields f JOIN slide_images si ON si.id=f.slide_image_id
               WHERE f.id=?""",
            (int(field_id),),
        ).fetchone()
        if not field or int(field["project_id"]) != int(project_id):
            raise ValueError("Область не относится к выбранному проекту")
        for image_id in ids:
            image = con.execute(
                "SELECT project_id, thin_section_id FROM slide_images WHERE id=?", (int(image_id),)
            ).fetchone()
            if not image or int(image["project_id"]) != int(project_id):
                raise ValueError("Один из снимков не относится к выбранному проекту")
            if field["thin_section_id"] is not None and image["thin_section_id"] is not None:
                if int(field["thin_section_id"]) != int(image["thin_section_id"]):
                    raise ValueError("Нельзя привязать к области снимок другого шлифа")
        con.execute(
            "DELETE FROM slide_field_image_links WHERE project_id=? AND field_id=?",
            (int(project_id), int(field_id)),
        )
        con.executemany(
            "INSERT INTO slide_field_image_links(project_id,field_id,image_id,note) VALUES(?,?,?,?)",
            [(int(project_id), int(field_id), int(image_id), str(note).strip()) for image_id in ids],
        )
        con.commit()


def list_field_image_links(project_id: int, *, field_id: int | None = None) -> list[dict]:
    ensure_region_image_schema()
    query = """
        SELECT l.field_id, l.image_id, l.note,
               f.name AS field_name, f.slide_image_id AS overview_image_id,
               detail.title AS image_title, detail.image_type, detail.preview_path,
               detail.thin_section_id
        FROM slide_field_image_links l
        JOIN slide_fields f ON f.id=l.field_id
        JOIN slide_images detail ON detail.id=l.image_id
        WHERE l.project_id=? AND f.project_id=?
    """
    params: list[object] = [int(project_id), int(project_id)]
    if field_id is not None:
        query += " AND l.field_id=?"
        params.append(int(field_id))
    query += " ORDER BY f.name COLLATE NOCASE, detail.title COLLATE NOCASE"
    with connect() as con:
        rows = con.execute(query, params).fetchall()
    return [dict(row) for row in rows]
