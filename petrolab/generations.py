from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from petrolab.analysis_groups import WORK_GROUP_COLUMN, ensure_work_group_storage
from petrolab.db import _utcnow, connect

PETROLAB_GENERATION_COLUMN = "PetroLab Generation"
SOURCE_GENERATION_COLUMN = "Source Generation"
_SQL_CHUNK = 800


def _clean_ids(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _chunks(values: list[str], size: int = _SQL_CHUNK):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def ensure_generation_storage() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_generations (
                analysis_id TEXT PRIMARY KEY,
                generation_name TEXT NOT NULL,
                rationale TEXT NOT NULL DEFAULT '',
                source_kind TEXT NOT NULL DEFAULT 'manual',
                source_value TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_generation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id TEXT NOT NULL,
                previous_generation TEXT NOT NULL DEFAULT '',
                new_generation TEXT NOT NULL DEFAULT '',
                rationale TEXT NOT NULL DEFAULT '',
                source_kind TEXT NOT NULL DEFAULT 'manual',
                source_value TEXT NOT NULL DEFAULT '',
                changed_at TEXT NOT NULL,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_generation_name ON analysis_generations(generation_name)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_generation_history_analysis ON analysis_generation_history(analysis_id, id)")
        con.commit()


def generation_map() -> dict[str, str]:
    ensure_generation_storage()
    with connect() as con:
        rows = con.execute("SELECT analysis_id, generation_name FROM analysis_generations").fetchall()
    return {str(row["analysis_id"]): str(row["generation_name"]) for row in rows}


def assign_generation(
    analysis_ids: Iterable[str],
    generation_name: str,
    *,
    rationale: str = "",
    source_kind: str = "manual",
    source_value: str = "",
) -> int:
    ensure_generation_storage()
    ids = _clean_ids(analysis_ids)
    name = str(generation_name).strip()
    if not ids:
        return 0
    if not name:
        raise ValueError("Название Generation не может быть пустым")
    now = _utcnow()
    with connect() as con:
        existing: set[str] = set()
        for chunk in _chunks(ids):
            rows = con.execute(
                "SELECT analysis_id FROM analysis_rows WHERE analysis_id IN (" + ",".join("?" for _ in chunk) + ")",
                chunk,
            ).fetchall()
            existing.update(str(row["analysis_id"]) for row in rows)
        missing = [analysis_id for analysis_id in ids if analysis_id not in existing]
        if missing:
            raise ValueError(f"Не найдено анализов: {len(missing)}")
        previous: dict[str, str] = {}
        for chunk in _chunks(ids):
            rows = con.execute(
                "SELECT analysis_id, generation_name FROM analysis_generations WHERE analysis_id IN (" + ",".join("?" for _ in chunk) + ")",
                chunk,
            ).fetchall()
            previous.update({str(row["analysis_id"]): str(row["generation_name"]) for row in rows})
        con.executemany(
            """
            INSERT INTO analysis_generation_history(
                analysis_id, previous_generation, new_generation, rationale, source_kind, source_value, changed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (analysis_id, previous.get(analysis_id, ""), name, str(rationale).strip(), str(source_kind).strip() or "manual", str(source_value).strip(), now)
                for analysis_id in ids
            ],
        )
        con.executemany(
            """
            INSERT INTO analysis_generations(analysis_id, generation_name, rationale, source_kind, source_value, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(analysis_id) DO UPDATE SET
                generation_name=excluded.generation_name,
                rationale=excluded.rationale,
                source_kind=excluded.source_kind,
                source_value=excluded.source_value,
                updated_at=excluded.updated_at
            """,
            [(analysis_id, name, str(rationale).strip(), str(source_kind).strip() or "manual", str(source_value).strip(), now) for analysis_id in ids],
        )
        con.commit()
    return len(ids)


def clear_generation(analysis_ids: Iterable[str], *, rationale: str = "") -> int:
    ensure_generation_storage()
    ids = _clean_ids(analysis_ids)
    if not ids:
        return 0
    now = _utcnow()
    with connect() as con:
        previous: dict[str, str] = {}
        for chunk in _chunks(ids):
            rows = con.execute(
                "SELECT analysis_id, generation_name FROM analysis_generations WHERE analysis_id IN (" + ",".join("?" for _ in chunk) + ")",
                chunk,
            ).fetchall()
            previous.update({str(row["analysis_id"]): str(row["generation_name"]) for row in rows})
        if not previous:
            return 0
        con.executemany(
            """INSERT INTO analysis_generation_history(
                analysis_id, previous_generation, new_generation, rationale, source_kind, source_value, changed_at
            ) VALUES (?, ?, '', ?, 'manual_clear', '', ?)""",
            [(analysis_id, generation, str(rationale).strip(), now) for analysis_id, generation in previous.items()],
        )
        con.executemany("DELETE FROM analysis_generations WHERE analysis_id=?", [(analysis_id,) for analysis_id in previous])
        con.commit()
    return len(previous)


def promote_work_group(work_group: str, generation_name: str, *, rationale: str = "") -> int:
    ensure_work_group_storage()
    name = str(work_group).strip()
    if not name:
        raise ValueError("Укажите рабочую группу")
    with connect() as con:
        rows = con.execute("SELECT analysis_id FROM analysis_work_groups WHERE group_name=?", (name,)).fetchall()
    ids = [str(row["analysis_id"]) for row in rows]
    if not ids:
        raise ValueError("В рабочей группе нет анализов")
    return assign_generation(ids, generation_name, rationale=rationale, source_kind="work_group", source_value=name)


def generation_history(analysis_ids: Iterable[str] | None = None) -> list[dict]:
    ensure_generation_storage()
    with connect() as con:
        if analysis_ids is None:
            rows = con.execute("SELECT * FROM analysis_generation_history ORDER BY id DESC").fetchall()
        else:
            ids = _clean_ids(analysis_ids)
            if not ids:
                return []
            result = []
            for chunk in _chunks(ids):
                result.extend(con.execute(
                    "SELECT * FROM analysis_generation_history WHERE analysis_id IN (" + ",".join("?" for _ in chunk) + ") ORDER BY id DESC",
                    chunk,
                ).fetchall())
            rows = result
    return [dict(row) for row in rows]


def attach_generations(dataframe: pd.DataFrame) -> pd.DataFrame:
    result = dataframe.copy()
    if "Generation" in result.columns and SOURCE_GENERATION_COLUMN not in result.columns:
        result[SOURCE_GENERATION_COLUMN] = result["Generation"]
    if result.empty or "_analysis_id" not in result.columns:
        if PETROLAB_GENERATION_COLUMN not in result.columns:
            result[PETROLAB_GENERATION_COLUMN] = pd.Series(index=result.index, dtype="object")
        return result
    mapping = generation_map()
    result[PETROLAB_GENERATION_COLUMN] = [mapping.get(str(value), "") for value in result["_analysis_id"]]
    return result
