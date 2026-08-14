from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from petrolab.db import connect
from petrolab.minerals.registry import MINERALS


@dataclass(frozen=True)
class MineralAssignmentChange:
    analysis_id: str
    dataset_id: int
    previous_mineral_key: str
    mineral_key: str
    changed: bool


def ensure_mineral_assignment_storage() -> None:
    """Store an interpretation separately from source chemistry and the dataset default."""
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_mineral_assignments (
                analysis_id TEXT PRIMARY KEY,
                dataset_id INTEGER NOT NULL,
                mineral_key TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                assigned_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS mineral_assignment_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id TEXT NOT NULL,
                dataset_id INTEGER NOT NULL,
                previous_mineral_key TEXT NOT NULL DEFAULT '',
                mineral_key TEXT NOT NULL DEFAULT '',
                reason TEXT NOT NULL DEFAULT '',
                changed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_mineral_assignment_dataset ON analysis_mineral_assignments(dataset_id)"
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_mineral_assignment_history_analysis ON mineral_assignment_history(analysis_id, id DESC)"
        )
        con.commit()


def _validate_mineral_key(mineral_key: str) -> str:
    key = str(mineral_key or "").strip()
    if key not in MINERALS:
        raise ValueError("Неизвестный минералогический модуль: " + key)
    return key


def _assignment_row(analysis_id: str) -> dict:
    with connect() as con:
        row = con.execute(
            """
            SELECT a.analysis_id, a.dataset_id, d.mineral_key AS dataset_mineral_key,
                   ma.mineral_key AS assigned_mineral_key
            FROM analysis_rows a
            JOIN datasets d ON d.id=a.dataset_id
            LEFT JOIN analysis_mineral_assignments ma ON ma.analysis_id=a.analysis_id
            WHERE a.analysis_id=?
            """,
            (str(analysis_id),),
        ).fetchone()
    if row is None:
        raise KeyError("Анализ не найден")
    return dict(row)


def assign_mineral(
    analysis_id: str,
    mineral_key: str | None,
    *,
    reason: str = "",
) -> MineralAssignmentChange:
    """Assign one point to a mineral module or reset it to the dataset interpretation.

    The source row and the original dataset mineral never change.  A reassignment is an
    interpretation event, allowing an outlier found on a plot to be reviewed later.
    """
    ensure_mineral_assignment_storage()
    row = _assignment_row(analysis_id)
    dataset_key = str(row["dataset_mineral_key"])
    previous = str(row["assigned_mineral_key"] or dataset_key)
    requested = dataset_key if mineral_key is None else _validate_mineral_key(mineral_key)
    explicit_previous = str(row["assigned_mineral_key"] or "")
    if previous == requested and ((requested != dataset_key) == bool(explicit_previous)):
        return MineralAssignmentChange(str(analysis_id), int(row["dataset_id"]), previous, requested, False)

    clean_reason = str(reason or "").strip()
    with connect() as con:
        if requested == dataset_key:
            con.execute("DELETE FROM analysis_mineral_assignments WHERE analysis_id=?", (str(analysis_id),))
        else:
            con.execute(
                """
                INSERT INTO analysis_mineral_assignments(
                    analysis_id, dataset_id, mineral_key, reason, assigned_at
                ) VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(analysis_id) DO UPDATE SET
                    dataset_id=excluded.dataset_id,
                    mineral_key=excluded.mineral_key,
                    reason=excluded.reason,
                    assigned_at=CURRENT_TIMESTAMP
                """,
                (str(analysis_id), int(row["dataset_id"]), requested, clean_reason),
            )
        con.execute(
            """
            INSERT INTO mineral_assignment_history(
                analysis_id, dataset_id, previous_mineral_key, mineral_key, reason
            ) VALUES (?, ?, ?, ?, ?)
            """,
            (str(analysis_id), int(row["dataset_id"]), previous, requested, clean_reason),
        )
        con.commit()
    return MineralAssignmentChange(str(analysis_id), int(row["dataset_id"]), previous, requested, True)


def assignment_history(analysis_id: str) -> list[dict]:
    ensure_mineral_assignment_storage()
    with connect() as con:
        rows = con.execute(
            """
            SELECT previous_mineral_key, mineral_key, reason, changed_at
            FROM mineral_assignment_history
            WHERE analysis_id=?
            ORDER BY id DESC
            """,
            (str(analysis_id),),
        ).fetchall()
    return [dict(row) for row in rows]


def attach_mineral_assignments(
    dataframe: pd.DataFrame,
    *,
    default_mineral_key: str | None = None,
) -> pd.DataFrame:
    """Overlay point-level mineral interpretation onto a dataframe without mutating it."""
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        return dataframe.copy()
    ensure_mineral_assignment_storage()
    out = dataframe.copy()
    analysis_ids = out["_analysis_id"].astype(str).tolist()
    marks = ",".join("?" for _ in analysis_ids)
    with connect() as con:
        rows = con.execute(
            f"""
            SELECT analysis_id, mineral_key, reason, assigned_at
            FROM analysis_mineral_assignments
            WHERE analysis_id IN ({marks})
            """,
            analysis_ids,
        ).fetchall()
    assigned = {str(row["analysis_id"]): dict(row) for row in rows}

    if "Минерал" in out.columns:
        base = out["Минерал"].astype("string").fillna("")
    else:
        base = pd.Series(str(default_mineral_key or ""), index=out.index, dtype="string")
        out["Минерал"] = base
    out["Минерал исходного набора"] = base
    keys = out["_analysis_id"].astype(str)
    out["Минерал назначен вручную"] = keys.map(lambda value: value in assigned)
    out["Комментарий переотнесения"] = keys.map(
        lambda value: str(assigned.get(value, {}).get("reason") or "")
    )
    out["Переотнесено"] = keys.map(
        lambda value: str(assigned.get(value, {}).get("assigned_at") or "")
    )
    override = keys.map(lambda value: str(assigned.get(value, {}).get("mineral_key") or ""))
    out["Минерал"] = override.where(override.str.len() > 0, base)
    return out


def assigned_mineral_keys(analysis_ids: Iterable[str]) -> dict[str, str]:
    ids = [str(value) for value in analysis_ids]
    if not ids:
        return {}
    ensure_mineral_assignment_storage()
    marks = ",".join("?" for _ in ids)
    with connect() as con:
        rows = con.execute(
            f"SELECT analysis_id, mineral_key FROM analysis_mineral_assignments WHERE analysis_id IN ({marks})",
            ids,
        ).fetchall()
    return {str(row["analysis_id"]): str(row["mineral_key"]) for row in rows}
