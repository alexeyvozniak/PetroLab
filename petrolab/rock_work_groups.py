"""Локальные рабочие классы whole-rock точек/определений без изменения исходной химии."""
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from petrolab.repositories.rock_repository import rock_connection


ROCK_WORK_GROUP_COLUMN = "Рабочий класс породы"
ROCK_SELECTION_ID_COLUMN = "_rock_selection_id"


def ensure_rock_work_group_schema() -> None:
    with rock_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS rock_work_groups (
                selection_id TEXT PRIMARY KEY,
                group_name TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_rock_work_groups_name ON rock_work_groups(group_name)"
        )
        con.commit()


def rock_selection_id(rock_id: object, determination_id: object = None) -> str:
    """Определение имеет приоритет; legacy whole-rock строка идентифицируется физическим sample."""
    try:
        if determination_id is not None and not pd.isna(determination_id):
            return f"d:{int(determination_id)}"
    except (TypeError, ValueError):
        pass
    try:
        if rock_id is not None and not pd.isna(rock_id):
            return f"r:{int(rock_id)}"
    except (TypeError, ValueError):
        pass
    return ""


def attach_rock_selection_ids(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()
    if result.empty:
        result[ROCK_SELECTION_ID_COLUMN] = pd.Series(index=result.index, dtype="object")
        return result
    rock_ids = result.get("_rock_id", pd.Series(index=result.index, dtype="object"))
    determination_ids = result.get("_determination_id", pd.Series(index=result.index, dtype="object"))
    result[ROCK_SELECTION_ID_COLUMN] = [
        rock_selection_id(rock_id, determination_id)
        for rock_id, determination_id in zip(rock_ids, determination_ids)
    ]
    return result


def _clean_ids(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def set_rock_work_group(selection_ids: Iterable[str], group_name: str) -> int:
    """Присвоить выбранным whole-rock строкам обратимый рабочий класс."""
    ensure_rock_work_group_schema()
    ids = _clean_ids(selection_ids)
    name = str(group_name).strip()
    if not ids:
        return 0
    if not name:
        raise ValueError("Название рабочего класса не может быть пустым")
    invalid = [value for value in ids if not (value.startswith("d:") or value.startswith("r:"))]
    if invalid:
        raise ValueError("Есть строки без устойчивого whole-rock идентификатора")
    with rock_connection() as con:
        con.executemany(
            """
            INSERT INTO rock_work_groups(selection_id, group_name, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(selection_id) DO UPDATE SET
                group_name=excluded.group_name,
                updated_at=CURRENT_TIMESTAMP
            """,
            [(value, name) for value in ids],
        )
        con.commit()
    return len(ids)


def clear_rock_work_group(selection_ids: Iterable[str]) -> int:
    ensure_rock_work_group_schema()
    ids = _clean_ids(selection_ids)
    if not ids:
        return 0
    with rock_connection() as con:
        before = con.total_changes
        con.executemany("DELETE FROM rock_work_groups WHERE selection_id=?", [(value,) for value in ids])
        changed = con.total_changes - before
        con.commit()
    return int(changed)


def rock_work_group_map() -> dict[str, str]:
    ensure_rock_work_group_schema()
    with rock_connection() as con:
        rows = con.execute(
            "SELECT selection_id, group_name FROM rock_work_groups ORDER BY group_name, selection_id"
        ).fetchall()
    return {str(row["selection_id"]): str(row["group_name"]) for row in rows}


def list_rock_work_groups() -> list[str]:
    ensure_rock_work_group_schema()
    with rock_connection() as con:
        rows = con.execute(
            "SELECT DISTINCT group_name FROM rock_work_groups ORDER BY group_name COLLATE NOCASE"
        ).fetchall()
    return [str(row["group_name"]) for row in rows]


def attach_rock_work_groups(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = attach_rock_selection_ids(dataframe)
    mapping = rock_work_group_map()
    result[ROCK_WORK_GROUP_COLUMN] = [
        mapping.get(str(value), "") for value in result[ROCK_SELECTION_ID_COLUMN]
    ]
    return result
