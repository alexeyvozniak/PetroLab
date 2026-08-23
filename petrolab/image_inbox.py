"""A durable staging area for images awaiting scientific context.

Files may arrive before the user decides whether they belong to a Sample,
field or an analytical point.  Inbox keeps them visible and unassigned instead
of forcing a guessed link during upload.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from petrolab.db import ASSETS_DIR, _utcnow, connect
from petrolab.services.image_service import ImageAssignment, ImagePayload, create_assigned_image_batch


@dataclass(frozen=True)
class InboxItem:
    id: int
    project_id: int
    filename: str
    stored_path: str
    added_at: str
    assigned_asset_id: int | None
    note: str


def ensure_inbox_schema() -> None:
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS image_inbox_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                stored_path TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                assigned_asset_id INTEGER,
                added_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(assigned_asset_id) REFERENCES image_assets(id) ON DELETE SET NULL
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_image_inbox_project ON image_inbox_items(project_id, assigned_asset_id)")
        con.commit()


def _dir(project_id: int) -> Path:
    target = ASSETS_DIR / "image_inbox" / f"project_{int(project_id)}"
    target.mkdir(parents=True, exist_ok=True)
    return target


def add_to_inbox(project_id: int, payloads: list[ImagePayload]) -> list[InboxItem]:
    """Validate all payloads before writing a single Inbox item."""
    # Reuse the production image validator without exposing an unsafe upload path.
    from petrolab.services.image_service import _validate_payload
    ensure_inbox_schema()
    if not payloads:
        raise ValueError("Выберите хотя бы одно изображение")
    for payload in payloads:
        _validate_payload(payload)
    written: list[Path] = []
    ids: list[int] = []
    try:
        with connect() as con:
            for payload in payloads:
                filename = Path(payload.filename).name
                target = _dir(project_id) / f"{uuid4().hex}_{filename}"
                target.write_bytes(payload.data)
                written.append(target)
                cur = con.execute(
                    "INSERT INTO image_inbox_items(project_id,filename,stored_path,added_at) VALUES(?,?,?,?)",
                    (int(project_id), filename, str(target), _utcnow()),
                )
                ids.append(int(cur.lastrowid))
            con.commit()
    except Exception:
        for path in written:
            path.unlink(missing_ok=True)
        raise
    return [item for item in list_inbox_items(project_id, include_assigned=True) if item.id in set(ids)]


def list_inbox_items(project_id: int, *, include_assigned: bool = False) -> list[InboxItem]:
    ensure_inbox_schema()
    query = "SELECT * FROM image_inbox_items WHERE project_id=?"
    if not include_assigned:
        query += " AND assigned_asset_id IS NULL"
    query += " ORDER BY added_at DESC, id DESC"
    with connect() as con:
        rows = con.execute(query, (int(project_id),)).fetchall()
    return [InboxItem(**dict(row)) for row in rows]


def assign_inbox_item(project_id: int, item_id: int, *, dataset_id: int, assignment: ImageAssignment) -> int:
    """Turn exactly one staged file into a regular, fully linked image asset."""
    ensure_inbox_schema()
    with connect() as con:
        row = con.execute("SELECT * FROM image_inbox_items WHERE id=? AND project_id=?", (int(item_id), int(project_id))).fetchone()
    if row is None:
        raise KeyError("Изображение Inbox не найдено")
    if row["assigned_asset_id"] is not None:
        raise ValueError("Это изображение уже было привязано")
    path = Path(str(row["stored_path"]))
    if not path.is_file():
        raise ValueError("Файл Inbox отсутствует на диске; удалите запись или загрузите файл повторно")
    payload = ImagePayload(str(row["filename"]), path.read_bytes())
    result = create_assigned_image_batch(
        project_id=int(project_id), dataset_id=int(dataset_id),
        assignments=[ImageAssignment(payload, assignment.scope, assignment.kind, assignment.title or path.stem)],
    )
    asset_id = int(result.asset_ids[0])
    with connect() as con:
        con.execute("UPDATE image_inbox_items SET assigned_asset_id=? WHERE id=?", (asset_id, int(item_id)))
        con.commit()
    path.unlink(missing_ok=True)
    return asset_id


def assign_inbox_items(
    project_id: int,
    item_ids: list[int],
    *,
    dataset_id: int,
    scope,
    kind: str,
    title: str = "",
) -> list[int]:
    """Assign several staged images to one explicitly chosen scientific context.

    The production image service validates the entire list before writing a file,
    so an invalid common scope cannot leave half of the Inbox attached.
    """
    ensure_inbox_schema()
    unique_ids = list(dict.fromkeys(int(value) for value in item_ids))
    if not unique_ids:
        raise ValueError("Выберите изображения Inbox")
    markers = ",".join("?" for _ in unique_ids)
    with connect() as con:
        rows = con.execute(
            f"SELECT * FROM image_inbox_items WHERE project_id=? AND id IN ({markers})",
            (int(project_id), *unique_ids),
        ).fetchall()
    by_id = {int(row["id"]): row for row in rows}
    if set(by_id) != set(unique_ids):
        raise ValueError("Часть выбранных изображений Inbox недоступна")
    if any(row["assigned_asset_id"] is not None for row in rows):
        raise ValueError("Часть выбранных изображений уже была привязана")
    assignments: list[ImageAssignment] = []
    paths: list[Path] = []
    for item_id in unique_ids:
        row = by_id[item_id]
        path = Path(str(row["stored_path"]))
        if not path.is_file():
            raise ValueError(f"Файл Inbox отсутствует: {row['filename']}")
        paths.append(path)
        assignments.append(ImageAssignment(
            ImagePayload(str(row["filename"]), path.read_bytes()), scope, str(kind),
            str(title).strip() or path.stem,
        ))
    result = create_assigned_image_batch(
        project_id=int(project_id), dataset_id=int(dataset_id), assignments=assignments,
    )
    with connect() as con:
        con.executemany(
            "UPDATE image_inbox_items SET assigned_asset_id=? WHERE id=?",
            list(zip(result.asset_ids, unique_ids)),
        )
        con.commit()
    for path in paths:
        path.unlink(missing_ok=True)
    return list(result.asset_ids)


def discard_inbox_item(project_id: int, item_id: int) -> None:
    ensure_inbox_schema()
    with connect() as con:
        row = con.execute("SELECT stored_path FROM image_inbox_items WHERE id=? AND project_id=?", (int(item_id), int(project_id))).fetchone()
        if row is None:
            return
        con.execute("DELETE FROM image_inbox_items WHERE id=?", (int(item_id),))
        con.commit()
    Path(str(row["stored_path"])).unlink(missing_ok=True)
