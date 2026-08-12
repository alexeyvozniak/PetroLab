from __future__ import annotations

import io
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from PIL import Image

from petrolab.db import ASSETS_DIR, DB_PATH


ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_image(content: bytes, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Неподдерживаемый формат изображения: {suffix or 'без расширения'}")
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
    except Exception as exc:
        raise ValueError(f"Файл {filename} не является корректным изображением") from exc
    return suffix


def save_rock_image(rock_id: int, filename: str, content: bytes, *, kind: str = "Фото породы", title: str = "") -> int:
    suffix = _validate_image(content, filename)
    directory = ASSETS_DIR / "rocks" / str(int(rock_id))
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid4().hex}{suffix}"
    path.write_bytes(content)
    try:
        con = sqlite3.connect(DB_PATH)
        try:
            con.execute("PRAGMA foreign_keys=ON")
            cur = con.execute(
                "INSERT INTO rock_images(rock_id, kind, title, original_filename, stored_path, added_at) VALUES (?, ?, ?, ?, ?, ?)",
                (int(rock_id), kind, title, filename, str(path), _utcnow()),
            )
            con.commit()
            return int(cur.lastrowid)
        finally:
            con.close()
    except Exception:
        path.unlink(missing_ok=True)
        raise


def list_rock_images(rock_id: int) -> list[dict]:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute("SELECT * FROM rock_images WHERE rock_id=? ORDER BY added_at", (int(rock_id),)).fetchall()
    finally:
        con.close()
    return [dict(row) for row in rows]


def delete_rock_image(image_id: int) -> None:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute("SELECT stored_path FROM rock_images WHERE id=?", (int(image_id),)).fetchone()
        if row is None:
            return
        path = Path(str(row["stored_path"]))
        temporary = path.with_suffix(path.suffix + ".deleting")
        if path.exists():
            path.replace(temporary)
        try:
            con.execute("DELETE FROM rock_images WHERE id=?", (int(image_id),))
            con.commit()
            temporary.unlink(missing_ok=True)
        except Exception:
            if temporary.exists():
                temporary.replace(path)
            raise
    finally:
        con.close()
