from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

import pandas as pd

from petrolab.analysis_identity import ExistingAnalysis, match_existing_analyses
from petrolab.db import _json_safe_record, _utcnow, connect


@dataclass(frozen=True)
class RefreshPersistenceResult:
    row_count: int
    reused_count: int
    new_count: int
    removed_count: int
    moved_rows_detected: bool


def replace_dataset_rows_stable(
    dataset_id: int,
    dataframe: pd.DataFrame,
    source_rows: list[int | None],
) -> RefreshPersistenceResult:
    """Replace refreshed rows while conservatively preserving stable analysis IDs."""
    if len(source_rows) != len(dataframe):
        raise ValueError("Количество source_rows не совпадает с числом строк")

    now = _utcnow()
    with connect() as con:
        old_rows = con.execute(
            "SELECT analysis_id, source_row, data_json FROM analysis_rows WHERE dataset_id=?",
            (int(dataset_id),),
        ).fetchall()
        existing = [
            ExistingAnalysis(
                analysis_id=str(row["analysis_id"]),
                source_row=row["source_row"],
                data=json.loads(row["data_json"]),
            )
            for row in old_rows
        ]
        match = match_existing_analyses(existing, dataframe, source_rows)

        planned: list[tuple[str, int, int | None, str, bool]] = []
        for index, (_, row) in enumerate(dataframe.iterrows()):
            reused = index in match.matched_ids
            analysis_id = match.matched_ids.get(index, uuid4().hex)
            payload = json.dumps(_json_safe_record(row.to_dict()), ensure_ascii=False)
            planned.append((analysis_id, index, source_rows[index], payload, reused))

        removed_ids = set(match.unmatched_existing_ids)
        if removed_ids:
            marks = ",".join("?" for _ in removed_ids)
            # Keep image assets themselves. Only point-specific legacy links to rows that no
            # longer exist are cleared; many-to-many link rows cascade when available.
            con.execute(
                f"UPDATE image_assets SET analysis_id=NULL WHERE analysis_id IN ({marks})",
                list(removed_ids),
            )
            con.execute(
                f"DELETE FROM analysis_rows WHERE analysis_id IN ({marks})",
                list(removed_ids),
            )

        # Avoid transient UNIQUE(dataset_id, row_index) collisions while rows move.
        con.execute(
            "UPDATE analysis_rows SET row_index=-1000000-row_index WHERE dataset_id=?",
            (int(dataset_id),),
        )

        reused_ids = set(match.matched_ids.values())
        for analysis_id, row_index, source_row, payload, reused in planned:
            if reused and analysis_id in reused_ids:
                con.execute(
                    """
                    UPDATE analysis_rows
                    SET row_index=?, source_row=?, data_json=?, updated_at=?
                    WHERE analysis_id=? AND dataset_id=?
                    """,
                    (row_index, source_row, payload, now, analysis_id, int(dataset_id)),
                )
            else:
                con.execute(
                    """
                    INSERT INTO analysis_rows(
                        analysis_id, dataset_id, row_index, source_row, data_json, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (analysis_id, int(dataset_id), row_index, source_row, payload, now),
                )

        con.execute(
            "UPDATE datasets SET row_count=? WHERE id=?",
            (len(dataframe), int(dataset_id)),
        )
        con.commit()

    reused_count = len(match.matched_ids)
    return RefreshPersistenceResult(
        row_count=len(dataframe),
        reused_count=reused_count,
        new_count=len(dataframe) - reused_count,
        removed_count=len(match.unmatched_existing_ids),
        moved_rows_detected=match.moved_rows_detected,
    )
