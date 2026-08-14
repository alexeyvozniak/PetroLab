from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from petrolab.db import connect


@dataclass(frozen=True)
class SampleLocation:
    sample_id: int
    location: str
    note: str
    recorded_at: str


def ensure_sample_location_storage() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sample_location_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id INTEGER NOT NULL,
                location TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                recorded_at TEXT NOT NULL,
                FOREIGN KEY(sample_id) REFERENCES samples(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_sample_location_events_sample ON sample_location_events(sample_id, id DESC)"
        )
        con.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_sample_location(sample_id: int, location: str, *, note: str = "") -> SampleLocation:
    """Append a location event; former locations remain part of the specimen history."""
    ensure_sample_location_storage()
    clean = str(location or "").strip()
    if not clean:
        raise ValueError("Укажите, где сейчас находится образец")
    with connect() as con:
        exists = con.execute("SELECT id FROM samples WHERE id=?", (int(sample_id),)).fetchone()
        if exists is None:
            raise KeyError("Образец не найден")
        stamp = _now()
        con.execute(
            """
            INSERT INTO sample_location_events(sample_id, location, note, recorded_at)
            VALUES (?, ?, ?, ?)
            """,
            (int(sample_id), clean, str(note or "").strip(), stamp),
        )
        con.commit()
    return SampleLocation(int(sample_id), clean, str(note or "").strip(), stamp)


def current_sample_location(sample_id: int) -> SampleLocation | None:
    ensure_sample_location_storage()
    with connect() as con:
        row = con.execute(
            """
            SELECT sample_id, location, note, recorded_at
            FROM sample_location_events
            WHERE sample_id=?
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(sample_id),),
        ).fetchone()
    if row is None:
        return None
    return SampleLocation(
        int(row["sample_id"]), str(row["location"]), str(row["note"]), str(row["recorded_at"])
    )


def sample_location_history(sample_id: int, limit: int = 100) -> list[dict]:
    ensure_sample_location_storage()
    with connect() as con:
        rows = con.execute(
            """
            SELECT location, note, recorded_at
            FROM sample_location_events
            WHERE sample_id=?
            ORDER BY id DESC
            LIMIT ?
            """,
            (int(sample_id), int(limit)),
        ).fetchall()
    return [dict(row) for row in rows]


def current_locations(sample_ids: list[int]) -> dict[int, SampleLocation]:
    ids = [int(value) for value in sample_ids]
    if not ids:
        return {}
    ensure_sample_location_storage()
    marks = ",".join("?" for _ in ids)
    with connect() as con:
        rows = con.execute(
            f"""
            SELECT event.sample_id, event.location, event.note, event.recorded_at
            FROM sample_location_events event
            JOIN (
                SELECT sample_id, MAX(id) AS event_id
                FROM sample_location_events
                WHERE sample_id IN ({marks})
                GROUP BY sample_id
            ) latest ON latest.event_id=event.id
            """,
            ids,
        ).fetchall()
    return {
        int(row["sample_id"]): SampleLocation(
            int(row["sample_id"]), str(row["location"]), str(row["note"]), str(row["recorded_at"])
        )
        for row in rows
    }
