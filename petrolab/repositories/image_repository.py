from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from petrolab.db import connect


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_image_link_schema() -> None:
    """Create the many-to-many link table and migrate legacy single-point links."""
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS image_analysis_links (
                asset_id INTEGER NOT NULL,
                analysis_id TEXT NOT NULL,
                PRIMARY KEY(asset_id, analysis_id),
                FOREIGN KEY(asset_id) REFERENCES image_assets(id) ON DELETE CASCADE,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_image_links_analysis ON image_analysis_links(analysis_id)")
        con.execute(
            """
            INSERT OR IGNORE INTO image_analysis_links(asset_id, analysis_id)
            SELECT id, analysis_id FROM image_assets
            WHERE analysis_id IS NOT NULL AND analysis_id != ''
            """
        )
        con.commit()


def create_image_record(
    *,
    project_id: int,
    dataset_id: int,
    analysis_ids: Iterable[str],
    scope_type: str,
    scope_column: str,
    scope_value: str,
    kind: str,
    title: str,
    original_filename: str,
    stored_path: str,
) -> int:
    """Insert one physical image record plus zero or more point links."""
    ensure_image_link_schema()
    unique_ids = tuple(dict.fromkeys(str(value) for value in analysis_ids if value))
    legacy_analysis_id = unique_ids[0] if len(unique_ids) == 1 else None
    with connect() as con:
        cursor = con.execute(
            """
            INSERT INTO image_assets(
                project_id, dataset_id, analysis_id, scope_type, scope_column, scope_value,
                kind, title, original_filename, stored_path, added_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(project_id), int(dataset_id), legacy_analysis_id, scope_type,
                scope_column, scope_value, kind, title, original_filename, stored_path, _utcnow(),
            ),
        )
        asset_id = int(cursor.lastrowid)
        con.executemany(
            "INSERT INTO image_analysis_links(asset_id, analysis_id) VALUES (?, ?)",
            [(asset_id, analysis_id) for analysis_id in unique_ids],
        )
        con.commit()
        return asset_id


def get_image_record(asset_id: int) -> dict:
    ensure_image_link_schema()
    with connect() as con:
        row = con.execute("SELECT * FROM image_assets WHERE id=?", (int(asset_id),)).fetchone()
        if row is None:
            raise KeyError(f"Изображение {asset_id} не найдено")
        links = con.execute(
            "SELECT analysis_id FROM image_analysis_links WHERE asset_id=? ORDER BY analysis_id",
            (int(asset_id),),
        ).fetchall()
    result = dict(row)
    result["analysis_ids"] = [str(link["analysis_id"]) for link in links]
    return result


def list_image_records(
    *,
    project_id: int | None = None,
    dataset_id: int | None = None,
    analysis_id: str | None = None,
) -> list[dict]:
    ensure_image_link_schema()
    clauses: list[str] = []
    params: list[object] = []
    if project_id is not None:
        clauses.append("i.project_id=?")
        params.append(int(project_id))
    if dataset_id is not None:
        clauses.append("i.dataset_id=?")
        params.append(int(dataset_id))
    if analysis_id is not None:
        clauses.append(
            "EXISTS (SELECT 1 FROM image_analysis_links l WHERE l.asset_id=i.id AND l.analysis_id=?)"
        )
        params.append(str(analysis_id))
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    with connect() as con:
        rows = con.execute(
            f"""
            SELECT i.*, d.name AS dataset_name, p.name AS project_name
            FROM image_assets i
            LEFT JOIN datasets d ON d.id=i.dataset_id
            JOIN projects p ON p.id=i.project_id
            {where}
            ORDER BY i.added_at DESC
            """,
            params,
        ).fetchall()
        records = [dict(row) for row in rows]
        if not records:
            return []
        asset_ids = [int(record["id"]) for record in records]
        marks = ",".join("?" for _ in asset_ids)
        link_rows = con.execute(
            f"SELECT asset_id, analysis_id FROM image_analysis_links WHERE asset_id IN ({marks}) ORDER BY analysis_id",
            asset_ids,
        ).fetchall()

    linked: dict[int, list[str]] = {asset_id: [] for asset_id in asset_ids}
    for row in link_rows:
        linked[int(row["asset_id"])].append(str(row["analysis_id"]))
    for record in records:
        record["analysis_ids"] = linked[int(record["id"])]
    return records


def delete_image_record(asset_id: int) -> None:
    ensure_image_link_schema()
    with connect() as con:
        con.execute("DELETE FROM image_assets WHERE id=?", (int(asset_id),))
        con.commit()
