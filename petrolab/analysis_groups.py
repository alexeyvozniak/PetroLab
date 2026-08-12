from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from petrolab.db import _utcnow, connect


WORK_GROUP_COLUMN = "Рабочая группа"
_SQL_CHUNK = 800


def ensure_work_group_storage() -> None:
    """Create local analysis-group storage without modifying source analytical rows."""
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_work_groups (
                analysis_id TEXT PRIMARY KEY,
                group_name TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_analysis_work_groups_name "
            "ON analysis_work_groups(group_name)"
        )
        con.commit()


def _clean_ids(analysis_ids: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in analysis_ids if str(value).strip()})


def _chunks(values: list[str], size: int = _SQL_CHUNK):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def set_work_group(analysis_ids: Iterable[str], group_name: str) -> int:
    """Assign one local working group to one or more immutable analysis IDs."""
    ensure_work_group_storage()
    ids = _clean_ids(analysis_ids)
    name = str(group_name).strip()
    if not ids:
        return 0
    if not name:
        raise ValueError("Название рабочей группы не может быть пустым")

    now = _utcnow()
    with connect() as con:
        existing: set[str] = set()
        for chunk in _chunks(ids):
            rows = con.execute(
                "SELECT analysis_id FROM analysis_rows WHERE analysis_id IN ("
                + ",".join("?" for _ in chunk)
                + ")",
                chunk,
            ).fetchall()
            existing.update(str(row["analysis_id"]) for row in rows)
        missing = [analysis_id for analysis_id in ids if analysis_id not in existing]
        if missing:
            raise ValueError(
                f"Не найдено анализов: {len(missing)}. Обновите страницу и повторите выбор."
            )
        con.executemany(
            """
            INSERT INTO analysis_work_groups(analysis_id, group_name, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(analysis_id) DO UPDATE SET
                group_name=excluded.group_name,
                updated_at=excluded.updated_at
            """,
            [(analysis_id, name, now) for analysis_id in ids],
        )
        con.commit()
    return len(ids)


def clear_work_group(analysis_ids: Iterable[str]) -> int:
    ensure_work_group_storage()
    ids = _clean_ids(analysis_ids)
    if not ids:
        return 0
    with connect() as con:
        before = con.total_changes
        for chunk in _chunks(ids):
            con.execute(
                "DELETE FROM analysis_work_groups WHERE analysis_id IN ("
                + ",".join("?" for _ in chunk)
                + ")",
                chunk,
            )
        changed = con.total_changes - before
        con.commit()
    return int(changed)


def work_group_map() -> dict[str, str]:
    ensure_work_group_storage()
    with connect() as con:
        rows = con.execute(
            "SELECT analysis_id, group_name FROM analysis_work_groups ORDER BY group_name, analysis_id"
        ).fetchall()
    return {str(row["analysis_id"]): str(row["group_name"]) for row in rows}


def list_work_groups() -> list[str]:
    ensure_work_group_storage()
    with connect() as con:
        rows = con.execute(
            "SELECT DISTINCT group_name FROM analysis_work_groups ORDER BY group_name COLLATE NOCASE"
        ).fetchall()
    return [str(row["group_name"]) for row in rows]


def attach_work_groups(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Return a copy with local working groups joined by immutable _analysis_id."""
    result = dataframe.copy()
    if result.empty or "_analysis_id" not in result.columns:
        if WORK_GROUP_COLUMN not in result.columns:
            result[WORK_GROUP_COLUMN] = pd.Series(index=result.index, dtype="object")
        return result

    groups = work_group_map()
    result[WORK_GROUP_COLUMN] = [
        groups.get(str(analysis_id), "") for analysis_id in result["_analysis_id"]
    ]
    return result
