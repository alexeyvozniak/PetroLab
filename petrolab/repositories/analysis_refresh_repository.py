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
    detached_image_count: int = 0
    positional_reused_count: int = 0
    positional_fallback_disabled: bool = False


def _has_point_specific_metadata(con, dataset_id: int) -> bool:
    """Return True only when analysis IDs already carry point-specific user metadata."""
    legacy = con.execute(
        "SELECT 1 FROM image_assets WHERE dataset_id=? AND analysis_id IS NOT NULL LIMIT 1",
        (int(dataset_id),),
    ).fetchone()
    if legacy:
        return True

    has_link_table = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='image_analysis_links'"
    ).fetchone()
    if has_link_table:
        linked = con.execute(
            """
            SELECT 1
            FROM image_analysis_links l
            JOIN image_assets i ON i.id=l.asset_id
            WHERE i.dataset_id=?
            LIMIT 1
            """,
            (int(dataset_id),),
        ).fetchone()
        if linked:
            return True

    changed = con.execute(
        "SELECT 1 FROM change_log WHERE dataset_id=? AND analysis_id IS NOT NULL LIMIT 1",
        (int(dataset_id),),
    ).fetchone()
    return bool(changed)


def replace_dataset_rows_stable(
    dataset_id: int,
    dataframe: pd.DataFrame,
    source_rows: list[int | None],
) -> RefreshPersistenceResult:
    """Replace refreshed rows while conservatively preserving stable analysis IDs."""
    if len(source_rows) != len(dataframe):
        raise ValueError("Количество source_rows не совпадает с числом строк")

    now = _utcnow()
    detached_asset_ids: set[int] = set()
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
        protect_point_metadata = _has_point_specific_metadata(con, int(dataset_id))
        match = match_existing_analyses(
            existing,
            dataframe,
            source_rows,
            allow_source_row_fallback=not protect_point_metadata,
        )

        planned: list[tuple[str, int, int | None, str, bool]] = []
        for index, (_, row) in enumerate(dataframe.iterrows()):
            reused = index in match.matched_ids
            analysis_id = match.matched_ids.get(index, uuid4().hex)
            payload = json.dumps(_json_safe_record(row.to_dict()), ensure_ascii=False)
            planned.append((analysis_id, index, source_rows[index], payload, reused))

        removed_ids = set(match.unmatched_existing_ids)
        if removed_ids:
            marks = ",".join("?" for _ in removed_ids)
            params = list(removed_ids)

            legacy_assets = con.execute(
                f"SELECT id FROM image_assets WHERE analysis_id IN ({marks})",
                params,
            ).fetchall()
            detached_asset_ids.update(int(row["id"]) for row in legacy_assets)

            has_link_table = con.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='image_analysis_links'"
            ).fetchone()
            if has_link_table:
                linked_assets = con.execute(
                    f"SELECT DISTINCT asset_id FROM image_analysis_links WHERE analysis_id IN ({marks})",
                    params,
                ).fetchall()
                detached_asset_ids.update(int(row["asset_id"]) for row in linked_assets)

            # Keep physical image assets. Links to analyses that no longer exist are detached;
            # many-to-many rows cascade on analysis deletion when that table exists.
            con.execute(
                f"UPDATE image_assets SET analysis_id=NULL WHERE analysis_id IN ({marks})",
                params,
            )
            con.execute(
                f"DELETE FROM analysis_rows WHERE analysis_id IN ({marks})",
                params,
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
        detached_image_count=len(detached_asset_ids),
        positional_reused_count=sum(
            1 for strategy in match.strategies.values() if strategy == "source-row"
        ),
        positional_fallback_disabled=match.positional_fallback_disabled,
    )
