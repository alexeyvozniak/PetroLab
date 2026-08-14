"""Lightweight slide photographs, fields and spatial analytical markers.

The original microscope image is intentionally *not* put in SQLite.  A record
keeps either a link to the local master file or an explicitly requested
portable copy.  PetroLab uses a smaller preview for the interface, which keeps
ordinary projects responsive even when the master is a multi-gigabyte TIFF.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageOps

from petrolab.db import ASSETS_DIR, connect
from petrolab.measurement_registry import ensure_measurement_registry_schema


IMAGE_TYPES = ("Фотография шлифа", "BSE", "EDS-карта", "LA-ICP-MS-карта", "Другое")
STORAGE_LINKED = "linked"
STORAGE_MANAGED = "managed"
PREVIEW_MAX_SIDE = 2560


@dataclass(frozen=True)
class SlideImage:
    id: int
    project_id: int
    thin_section_id: int | None
    title: str
    image_type: str
    storage_mode: str
    original_filename: str
    source_path: str
    managed_path: str
    preview_path: str
    content_sha256: str
    pixel_width: int
    pixel_height: int

    @property
    def original_available(self) -> bool:
        return bool(_master_path(self))


def ensure_slide_schema() -> None:
    """Create additive tables only when the slide module is opened."""
    ensure_measurement_registry_schema()
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS slide_images (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                thin_section_id INTEGER,
                title TEXT NOT NULL,
                image_type TEXT NOT NULL DEFAULT 'Фотография шлифа',
                storage_mode TEXT NOT NULL DEFAULT 'linked',
                original_filename TEXT NOT NULL,
                source_path TEXT NOT NULL DEFAULT '',
                managed_path TEXT NOT NULL DEFAULT '',
                preview_path TEXT NOT NULL,
                content_sha256 TEXT NOT NULL DEFAULT '',
                pixel_width INTEGER NOT NULL DEFAULT 0,
                pixel_height INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(thin_section_id) REFERENCES physical_entities(id) ON DELETE SET NULL
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_slide_images_project ON slide_images(project_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_slide_images_section ON slide_images(thin_section_id)")
        con.execute(
            """CREATE TABLE IF NOT EXISTS slide_fields (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                slide_image_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                geometry_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(slide_image_id, name),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(slide_image_id) REFERENCES slide_images(id) ON DELETE CASCADE
            )"""
        )
        con.execute(
            """CREATE TABLE IF NOT EXISTS slide_markers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                slide_image_id INTEGER NOT NULL,
                field_id INTEGER,
                entity_id INTEGER,
                label TEXT NOT NULL DEFAULT '',
                x_norm REAL NOT NULL,
                y_norm REAL NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(slide_image_id) REFERENCES slide_images(id) ON DELETE CASCADE,
                FOREIGN KEY(field_id) REFERENCES slide_fields(id) ON DELETE SET NULL,
                FOREIGN KEY(entity_id) REFERENCES physical_entities(id) ON DELETE SET NULL
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_slide_markers_image ON slide_markers(slide_image_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_slide_markers_entity ON slide_markers(entity_id)")
        con.execute(
            """CREATE TABLE IF NOT EXISTS slide_marker_analysis_links (
                marker_id INTEGER NOT NULL,
                analysis_id TEXT NOT NULL,
                PRIMARY KEY(marker_id, analysis_id),
                FOREIGN KEY(marker_id) REFERENCES slide_markers(id) ON DELETE CASCADE,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_slide_marker_analysis ON slide_marker_analysis_links(analysis_id)")
        con.commit()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _preview_dir(project_id: int) -> Path:
    path = ASSETS_DIR / "slide_previews" / f"project_{int(project_id)}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _managed_dir(project_id: int) -> Path:
    path = ASSETS_DIR / "slide_masters" / f"project_{int(project_id)}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _create_preview(source: Path, project_id: int) -> tuple[str, int, int]:
    """Write a display-sized WebP and return its path and master dimensions."""
    token = uuid4().hex
    target = _preview_dir(project_id) / f"{token}.webp"
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        width, height = image.size
        image.thumbnail((PREVIEW_MAX_SIDE, PREVIEW_MAX_SIDE), Image.Resampling.LANCZOS)
        if image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA")
        if image.mode == "RGBA":
            background = Image.new("RGB", image.size, "white")
            background.paste(image, mask=image.getchannel("A"))
            image = background
        image.save(target, "WEBP", quality=88, method=6)
    return str(target), int(width), int(height)


def _validate_project_and_section(con, project_id: int, thin_section_id: int | None) -> None:
    if not con.execute("SELECT 1 FROM projects WHERE id=?", (int(project_id),)).fetchone():
        raise ValueError("Проект не найден")
    if thin_section_id is not None:
        row = con.execute(
            "SELECT project_id, kind FROM physical_entities WHERE id=?", (int(thin_section_id),)
        ).fetchone()
        if not row or int(row["project_id"]) != int(project_id) or str(row["kind"]) != "thin_section":
            raise ValueError("Выбранный препарат не относится к этому проекту")


def _record_from_row(row) -> SlideImage:
    return SlideImage(
        id=int(row["id"]), project_id=int(row["project_id"]), thin_section_id=row["thin_section_id"],
        title=str(row["title"]), image_type=str(row["image_type"]), storage_mode=str(row["storage_mode"]),
        original_filename=str(row["original_filename"]), source_path=str(row["source_path"]),
        managed_path=str(row["managed_path"]), preview_path=str(row["preview_path"]),
        content_sha256=str(row["content_sha256"]), pixel_width=int(row["pixel_width"]),
        pixel_height=int(row["pixel_height"]),
    )


def _master_path(image: SlideImage) -> Path | None:
    candidates = (image.managed_path, image.source_path) if image.storage_mode == STORAGE_MANAGED else (image.source_path, image.managed_path)
    for raw in candidates:
        path = Path(raw) if raw else None
        if path and path.is_file():
            return path
    return None


def register_linked_slide_image(
    project_id: int, *, source_path: str | Path, title: str, image_type: str = IMAGE_TYPES[0],
    thin_section_id: int | None = None,
) -> SlideImage:
    """Register a master kept by the user and generate only a lightweight preview."""
    ensure_slide_schema()
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError("Файл оригинала не найден. Укажите полный путь к изображению.")
    title = str(title).strip() or source.stem
    preview_path, width, height = _create_preview(source, int(project_id))
    try:
        with connect() as con:
            _validate_project_and_section(con, int(project_id), thin_section_id)
            cur = con.execute(
                """INSERT INTO slide_images(project_id,thin_section_id,title,image_type,storage_mode,
                       original_filename,source_path,preview_path,content_sha256,pixel_width,pixel_height)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (int(project_id), thin_section_id, title, str(image_type), STORAGE_LINKED, source.name,
                 str(source), preview_path, _sha256(source), width, height),
            )
            con.commit()
            row = con.execute("SELECT * FROM slide_images WHERE id=?", (int(cur.lastrowid),)).fetchone()
    except Exception:
        Path(preview_path).unlink(missing_ok=True)
        raise
    return _record_from_row(row)


def register_managed_slide_image(
    project_id: int, *, filename: str, data: bytes, title: str, image_type: str = IMAGE_TYPES[0],
    thin_section_id: int | None = None,
) -> SlideImage:
    """Store a portable master only after the caller has explicitly chosen this mode."""
    ensure_slide_schema()
    filename = Path(str(filename)).name
    if not filename or not data:
        raise ValueError("Выберите непустой файл изображения")
    master = _managed_dir(int(project_id)) / f"{uuid4().hex}_{filename}"
    master.write_bytes(data)
    try:
        return _register_managed_path(project_id, master, title, image_type, thin_section_id, filename)
    except Exception:
        master.unlink(missing_ok=True)
        raise


def _register_managed_path(project_id: int, master: Path, title: str, image_type: str, thin_section_id: int | None, filename: str) -> SlideImage:
    preview_path, width, height = _create_preview(master, int(project_id))
    try:
        with connect() as con:
            _validate_project_and_section(con, int(project_id), thin_section_id)
            cur = con.execute(
                """INSERT INTO slide_images(project_id,thin_section_id,title,image_type,storage_mode,
                       original_filename,managed_path,preview_path,content_sha256,pixel_width,pixel_height)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                (int(project_id), thin_section_id, str(title).strip() or Path(filename).stem, str(image_type),
                 STORAGE_MANAGED, filename, str(master), preview_path, _sha256(master), width, height),
            )
            con.commit()
            row = con.execute("SELECT * FROM slide_images WHERE id=?", (int(cur.lastrowid),)).fetchone()
    except Exception:
        Path(preview_path).unlink(missing_ok=True)
        raise
    return _record_from_row(row)


def list_slide_images(project_id: int) -> list[SlideImage]:
    ensure_slide_schema()
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM slide_images WHERE project_id=? ORDER BY created_at DESC, id DESC", (int(project_id),)
        ).fetchall()
    return [_record_from_row(row) for row in rows]


def relink_slide_original(image_id: int, source_path: str | Path) -> SlideImage:
    """Repair a moved linked original. The existing preview remains usable meanwhile."""
    ensure_slide_schema()
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise ValueError("Новый путь к оригиналу не найден")
    with connect() as con:
        row = con.execute("SELECT * FROM slide_images WHERE id=?", (int(image_id),)).fetchone()
        if not row:
            raise ValueError("Изображение не найдено")
        image = _record_from_row(row)
        con.execute(
            "UPDATE slide_images SET source_path=?, original_filename=?, content_sha256=? WHERE id=?",
            (str(source), source.name, _sha256(source), int(image_id)),
        )
        con.commit()
        row = con.execute("SELECT * FROM slide_images WHERE id=?", (int(image_id),)).fetchone()
    return _record_from_row(row)


def delete_slide_image(image_id: int) -> None:
    ensure_slide_schema()
    with connect() as con:
        row = con.execute("SELECT preview_path, managed_path FROM slide_images WHERE id=?", (int(image_id),)).fetchone()
        if not row:
            return
        con.execute("DELETE FROM slide_images WHERE id=?", (int(image_id),))
        con.commit()
    for raw_path in (str(row["preview_path"] or ""), str(row["managed_path"] or "")):
        if raw_path:
            Path(raw_path).unlink(missing_ok=True)


def _valid_norm(value: float, name: str) -> float:
    numeric = float(value)
    if not 0 <= numeric <= 1:
        raise ValueError(f"{name} должен быть между 0 и 100 %")
    return numeric


def create_slide_field(project_id: int, *, slide_image_id: int, name: str, description: str = "", geometry: dict | None = None) -> int:
    ensure_slide_schema()
    name = str(name).strip()
    if not name:
        raise ValueError("Назовите поле")
    payload = geometry or {}
    with connect() as con:
        row = con.execute("SELECT project_id FROM slide_images WHERE id=?", (int(slide_image_id),)).fetchone()
        if not row or int(row["project_id"]) != int(project_id):
            raise ValueError("Изображение не относится к этому проекту")
        cur = con.execute(
            "INSERT INTO slide_fields(project_id,slide_image_id,name,description,geometry_json) VALUES(?,?,?,?,?)",
            (int(project_id), int(slide_image_id), name, str(description).strip(), json.dumps(payload, ensure_ascii=False)),
        )
        con.commit()
        return int(cur.lastrowid)


def list_slide_fields(project_id: int, *, slide_image_id: int | None = None) -> list[dict]:
    ensure_slide_schema()
    query = "SELECT * FROM slide_fields WHERE project_id=?"
    params: list[object] = [int(project_id)]
    if slide_image_id is not None:
        query += " AND slide_image_id=?"
        params.append(int(slide_image_id))
    query += " ORDER BY name COLLATE NOCASE, id"
    with connect() as con:
        rows = con.execute(query, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["geometry"] = json.loads(str(item.pop("geometry_json") or "{}"))
        except json.JSONDecodeError:
            item["geometry"] = {}
        result.append(item)
    return result


def _validate_analysis_ids(con, project_id: int, analysis_ids: tuple[str, ...]) -> None:
    for analysis_id in analysis_ids:
        row = con.execute(
            """SELECT 1 FROM analysis_rows a JOIN project_dataset_links l ON l.dataset_id=a.dataset_id
               WHERE a.analysis_id=? AND l.project_id=?""", (str(analysis_id), int(project_id))
        ).fetchone()
        if not row:
            raise ValueError("Одна из выбранных точек не добавлена в этот проект")


def create_slide_marker(
    project_id: int, *, slide_image_id: int, x_norm: float, y_norm: float, label: str = "", note: str = "",
    field_id: int | None = None, entity_id: int | None = None, analysis_ids: tuple[str, ...] = (),
) -> int:
    """Place one physical location and attach any number of imported analyses to it."""
    ensure_slide_schema()
    x_norm, y_norm = _valid_norm(x_norm, "X"), _valid_norm(y_norm, "Y")
    analysis_ids = tuple(dict.fromkeys(str(value) for value in analysis_ids if str(value).strip()))
    with connect() as con:
        image = con.execute("SELECT project_id FROM slide_images WHERE id=?", (int(slide_image_id),)).fetchone()
        if not image or int(image["project_id"]) != int(project_id):
            raise ValueError("Изображение не относится к этому проекту")
        if field_id is not None:
            field = con.execute("SELECT project_id, slide_image_id FROM slide_fields WHERE id=?", (int(field_id),)).fetchone()
            if not field or int(field["project_id"]) != int(project_id) or int(field["slide_image_id"]) != int(slide_image_id):
                raise ValueError("Поле не относится к выбранному изображению")
        if entity_id is not None:
            entity = con.execute("SELECT project_id FROM physical_entities WHERE id=?", (int(entity_id),)).fetchone()
            if not entity or int(entity["project_id"]) != int(project_id):
                raise ValueError("Физическая точка не относится к этому проекту")
        _validate_analysis_ids(con, int(project_id), analysis_ids)
        cur = con.execute(
            """INSERT INTO slide_markers(project_id,slide_image_id,field_id,entity_id,label,x_norm,y_norm,note)
               VALUES(?,?,?,?,?,?,?,?)""",
            (int(project_id), int(slide_image_id), field_id, entity_id, str(label).strip(), x_norm, y_norm, str(note).strip()),
        )
        marker_id = int(cur.lastrowid)
        con.executemany(
            "INSERT INTO slide_marker_analysis_links(marker_id,analysis_id) VALUES(?,?)",
            [(marker_id, analysis_id) for analysis_id in analysis_ids],
        )
        con.commit()
        return marker_id


def list_slide_markers(project_id: int, *, slide_image_id: int | None = None) -> list[dict]:
    ensure_slide_schema()
    query = """SELECT m.*, e.name AS entity_name, e.kind AS entity_kind, f.name AS field_name
               FROM slide_markers m
               LEFT JOIN physical_entities e ON e.id=m.entity_id
               LEFT JOIN slide_fields f ON f.id=m.field_id
               WHERE m.project_id=?"""
    params: list[object] = [int(project_id)]
    if slide_image_id is not None:
        query += " AND m.slide_image_id=?"
        params.append(int(slide_image_id))
    query += " ORDER BY m.id"
    with connect() as con:
        rows = con.execute(query, params).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            links = con.execute(
                "SELECT analysis_id FROM slide_marker_analysis_links WHERE marker_id=? ORDER BY analysis_id", (int(item["id"]),)
            ).fetchall()
            item["analysis_ids"] = [str(link["analysis_id"]) for link in links]
            result.append(item)
    return result


def delete_slide_marker(marker_id: int) -> None:
    ensure_slide_schema()
    with connect() as con:
        con.execute("DELETE FROM slide_markers WHERE id=?", (int(marker_id),))
        con.commit()


def render_slide_overlay(image: SlideImage, markers: list[dict], fields: list[dict] | None = None) -> Image.Image:
    """Return a display proxy with simple, legible field/point annotations."""
    preview = Path(image.preview_path)
    if not preview.is_file():
        raise ValueError("Лёгкое превью не найдено; перепривяжите оригинал или добавьте изображение снова")
    with Image.open(preview) as source:
        canvas = source.convert("RGB").copy()
    draw = ImageDraw.Draw(canvas)
    width, height = canvas.size
    for field in fields or []:
        geometry = field.get("geometry") or {}
        if {"x", "y", "width", "height"}.issubset(geometry):
            x, y = float(geometry["x"]) * width, float(geometry["y"]) * height
            right = x + float(geometry["width"]) * width
            bottom = y + float(geometry["height"]) * height
            draw.rectangle((x, y, right, bottom), outline="#45D6C8", width=max(2, width // 700))
            draw.text((x + 5, y + 5), str(field.get("name") or "Поле"), fill="#0A3331", stroke_width=2, stroke_fill="white")
    radius = max(5, min(16, width // 140))
    for index, marker in enumerate(markers, 1):
        x, y = float(marker["x_norm"]) * width, float(marker["y_norm"]) * height
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill="#F26B4D", outline="white", width=2)
        label = str(marker.get("label") or marker.get("entity_name") or f"P{index}")
        draw.text((x + radius + 3, y - radius), label, fill="#452019", stroke_width=2, stroke_fill="white")
    return canvas
