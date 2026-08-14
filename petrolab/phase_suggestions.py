from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from petrolab.db import _utcnow, connect
from petrolab.mineral_recognition import (
    MINERAL_RECOGNITION_RULESET_VERSION,
    recognize_dataframe,
    recognize_mineral,
    score_candidates,
)

PHASE_SUGGESTION_RULESET_VERSION = MINERAL_RECOGNITION_RULESET_VERSION
SUGGESTED_MINERAL_COLUMN = "Suggested Mineral"
SUGGESTION_CONFIDENCE_COLUMN = "Mineral suggestion confidence"
SUGGESTION_REASON_COLUMN = "Mineral suggestion reason"
SUGGESTION_RULESET_COLUMN = "Mineral suggestion ruleset"


def score_phase_candidates(row: Mapping[str, Any]) -> dict[str, tuple[float, list[str]]]:
    """Compatibility wrapper around the versioned Mineral Recognition engine."""
    return {
        name: (candidate.score, list(candidate.reasons))
        for name, candidate in score_candidates(row).items()
    }


def suggest_phase(row: Mapping[str, Any]) -> tuple[str, str, str]:
    result = recognize_mineral(row)
    return result.target, result.confidence, "; ".join(result.reasons)


def attach_phase_suggestions(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Attach conservative, versioned suggestions without confirming any mineral automatically."""
    return recognize_dataframe(dataframe)


def materialize_confirmed_phases(source_dataset_id: int, assignments: Mapping[str, str]) -> dict[str, int]:
    """Move confirmed analyses from one mixed dataset into child mineral datasets.

    Analysis IDs, data_json, source row, image links and provenance remain intact. No rows are
    duplicated. Unassigned analyses stay in the source dataset.
    """
    clean = {
        str(analysis_id).strip(): str(mineral).strip()
        for analysis_id, mineral in assignments.items()
        if str(analysis_id).strip() and str(mineral).strip()
    }
    if not clean:
        return {}
    now = _utcnow()
    with connect() as con:
        source = con.execute("SELECT * FROM datasets WHERE id=?", (int(source_dataset_id),)).fetchone()
        if not source:
            raise ValueError("Исходный mixed dataset не найден")
        marks = ",".join("?" for _ in clean)
        rows = con.execute(
            f"SELECT analysis_id FROM analysis_rows WHERE dataset_id=? AND analysis_id IN ({marks})",
            [int(source_dataset_id), *clean.keys()],
        ).fetchall()
        existing = {str(row["analysis_id"]) for row in rows}
        missing = [analysis_id for analysis_id in clean if analysis_id not in existing]
        if missing:
            raise ValueError("Некоторые анализы не принадлежат исходному mixed dataset")

        columns = [
            str(row[1]) for row in con.execute("PRAGMA table_info(datasets)").fetchall()
            if str(row[1]) != "id"
        ]
        created: dict[str, int] = {}
        for mineral in sorted(set(clean.values())):
            values = {column: source[column] for column in columns}
            values["name"] = f"{source['name']} · {mineral}"
            values["mineral_key"] = mineral
            values["row_count"] = 0
            values["imported_at"] = now
            placeholders = ",".join("?" for _ in columns)
            cur = con.execute(
                f"INSERT INTO datasets({','.join(columns)}) VALUES ({placeholders})",
                [values[column] for column in columns],
            )
            child_id = int(cur.lastrowid)
            created[mineral] = child_id
            has_studies = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dataset_studies'"
            ).fetchone()
            study = con.execute(
                "SELECT study_id, source_table, source_note FROM dataset_studies WHERE dataset_id=?",
                (int(source_dataset_id),),
            ).fetchone() if has_studies else None
            if study:
                con.execute(
                    "INSERT OR REPLACE INTO dataset_studies(dataset_id, study_id, source_table, source_note) VALUES (?, ?, ?, ?)",
                    (child_id, study["study_id"], study["source_table"], study["source_note"]),
                )

        for mineral, child_id in created.items():
            ids = [analysis_id for analysis_id, assigned in clean.items() if assigned == mineral]
            marks = ",".join("?" for _ in ids)
            con.execute(
                f"UPDATE analysis_rows SET dataset_id=? WHERE dataset_id=? AND analysis_id IN ({marks})",
                [child_id, int(source_dataset_id), *ids],
            )
            moved = con.execute(
                "SELECT analysis_id FROM analysis_rows WHERE dataset_id=? ORDER BY source_row, analysis_id",
                (child_id,),
            ).fetchall()
            con.executemany(
                "UPDATE analysis_rows SET row_index=? WHERE analysis_id=?",
                [(index, row["analysis_id"]) for index, row in enumerate(moved)],
            )
            con.execute("UPDATE datasets SET row_count=? WHERE id=?", (len(moved), child_id))

        remaining = con.execute(
            "SELECT analysis_id FROM analysis_rows WHERE dataset_id=? ORDER BY source_row, analysis_id",
            (int(source_dataset_id),),
        ).fetchall()
        con.executemany(
            "UPDATE analysis_rows SET row_index=? WHERE analysis_id=?",
            [(index, row["analysis_id"]) for index, row in enumerate(remaining)],
        )
        con.execute("UPDATE datasets SET row_count=? WHERE id=?", (len(remaining), int(source_dataset_id)))
        con.commit()
    return created
