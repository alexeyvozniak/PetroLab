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


def _table_exists(con, name: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone())


def _has_point_specific_metadata(con, dataset_id: int) -> bool:
    """Protect IDs whenever user-authored metadata is attached to individual analyses."""
    legacy = con.execute(
        "SELECT 1 FROM image_assets WHERE dataset_id=? AND analysis_id IS NOT NULL LIMIT 1",
        (int(dataset_id),),
    ).fetchone()
    if legacy:
        return True

    if _table_exists(con, "image_analysis_links"):
        linked = con.execute(
            """
            SELECT 1 FROM image_analysis_links l
            JOIN image_assets i ON i.id=l.asset_id
            WHERE i.dataset_id=? LIMIT 1
            """,
            (int(dataset_id),),
        ).fetchone()
        if linked:
            return True

    if _table_exists(con, "analysis_work_groups"):
        grouped = con.execute(
            """
            SELECT 1 FROM analysis_work_groups g
            JOIN analysis_rows a ON a.analysis_id=g.analysis_id
            WHERE a.dataset_id=? LIMIT 1
            """,
            (int(dataset_id),),
        ).fetchone()
        if grouped:
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
    """Refresh rows while preserving identities and semantic source versions conservatively."""
    if len(source_rows) != len(dataframe):
        raise ValueError("Количество source_rows не совпадает с числом строк")

    now = _utcnow()
    detached_asset_ids: set[int] = set()
    with connect() as con:
        old_rows = con.execute(
            "SELECT analysis_id, source_row, data_json, updated_at FROM analysis_rows WHERE dataset_id=?",
            (int(dataset_id),),
        ).fetchall()
        old_data = {str(row["analysis_id"]): json.loads(row["data_json"]) for row in old_rows}
        old_versions = {str(row["analysis_id"]): str(row["updated_at"]) for row in old_rows}
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

        planned: list[tuple[str, int, int | None, dict, bool]] = []
        for index, (_, row) in enumerate(dataframe.iterrows()):
            reused = index in match.matched_ids
            analysis_id = match.matched_ids.get(index, uuid4().hex)
            payload = _json_safe_record(row.to_dict())
            planned.append((analysis_id, index, source_rows[index], payload, reused))

        removed_ids = set(match.unmatched_existing_ids)
        if removed_ids:
            marks = ",".join("?" for _ in removed_ids)
            params = list(removed_ids)
            legacy_assets = con.execute(
                f"SELECT id FROM image_assets WHERE analysis_id IN ({marks})", params
            ).fetchall()
            detached_asset_ids.update(int(row["id"]) for row in legacy_assets)

            if _table_exists(con, "image_analysis_links"):
                linked_assets = con.execute(
                    f"SELECT DISTINCT asset_id FROM image_analysis_links WHERE analysis_id IN ({marks})",
                    params,
                ).fetchall()
                detached_asset_ids.update(int(row["asset_id"]) for row in linked_assets)

            con.execute(f"UPDATE image_assets SET analysis_id=NULL WHERE analysis_id IN ({marks})", params)
            con.execute(f"DELETE FROM analysis_rows WHERE analysis_id IN ({marks})", params)

        con.execute(
            "UPDATE analysis_rows SET row_index=-1000000-row_index WHERE dataset_id=?",
            (int(dataset_id),),
        )

        reused_ids = set(match.matched_ids.values())
        for analysis_id, row_index, source_row, payload, reused in planned:
            payload_json = json.dumps(payload, ensure_ascii=False)
            if reused and analysis_id in reused_ids:
                # Moving a row or rereading an unchanged workbook is not a scientific edit.
                # Keep the source version when the actual source-layer payload is unchanged.
                updated_at = now if old_data.get(analysis_id) != payload else old_versions[analysis_id]
                con.execute(
                    """
                    UPDATE analysis_rows
                    SET row_index=?, source_row=?, data_json=?, updated_at=?
                    WHERE analysis_id=? AND dataset_id=?
                    """,
                    (row_index, source_row, payload_json, updated_at, analysis_id, int(dataset_id)),
                )
            else:
                con.execute(
                    """
                    INSERT INTO analysis_rows(analysis_id, dataset_id, row_index, source_row, data_json, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (analysis_id, int(dataset_id), row_index, source_row, payload_json, now),
                )

        con.execute("UPDATE datasets SET row_count=? WHERE id=?", (len(dataframe), int(dataset_id)))
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
