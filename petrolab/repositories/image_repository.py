from __future__ import annotations

from datetime import datetime, timezone

from petrolab.db import connect


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_image_record(
    *,
    project_id: int,
    dataset_id: int,
    analysis_id: str | None,
    scope_type: str,
    scope_column: str,
    scope_value: str,
    kind: str,
    title: str,
    original_filename: str,
    stored_path: str,
) -> int:
    """Insert one image metadata record and return its ID."""
    with connect() as con:
        cursor = con.execute(
            """
            INSERT INTO image_assets(
                project_id, dataset_id, analysis_id, scope_type, scope_column, scope_value,
                kind, title, original_filename, stored_path, added_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(project_id),
                int(dataset_id),
                analysis_id,
                scope_type,
                scope_column,
                scope_value,
                kind,
                title,
                original_filename,
                stored_path,
                _utcnow(),
            ),
        )
        con.commit()
        return int(cursor.lastrowid)


def get_image_record(asset_id: int) -> dict:
    """Return one image metadata record."""
    with connect() as con:
        row = con.execute("SELECT * FROM image_assets WHERE id=?", (int(asset_id),)).fetchone()
    if row is None:
        raise KeyError(f"Изображение {asset_id} не найдено")
    return dict(row)


def list_image_records(
    *,
    project_id: int | None = None,
    dataset_id: int | None = None,
    analysis_id: str | None = None,
) -> list[dict]:
    """List image metadata records filtered by project/dataset/analysis."""
    clauses: list[str] = []
    params: list[object] = []
    if project_id is not None:
        clauses.append("i.project_id=?")
        params.append(int(project_id))
    if dataset_id is not None:
        clauses.append("i.dataset_id=?")
        params.append(int(dataset_id))
    if analysis_id is not None:
        clauses.append("i.analysis_id=?")
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
    return [dict(row) for row in rows]


def delete_image_record(asset_id: int) -> None:
    """Delete only image metadata; filesystem cleanup belongs to the service layer."""
    with connect() as con:
        con.execute("DELETE FROM image_assets WHERE id=?", (int(asset_id),))
        con.commit()
