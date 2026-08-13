from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from petrolab.db import connect


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_analysis_changes(
    changes: list[dict[str, Any]],
    *,
    synced_to_source: bool,
) -> None:
    """Apply a whole edit batch in one transaction after validating row ownership."""
    if not changes:
        return

    grouped: dict[str, list[dict[str, Any]]] = {}
    for change in changes:
        grouped.setdefault(str(change["analysis_id"]), []).append(change)

    now = _utcnow()
    with connect() as con:
        for analysis_id, items in grouped.items():
            row = con.execute(
                "SELECT dataset_id, data_json FROM analysis_rows WHERE analysis_id=?",
                (analysis_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"Анализ {analysis_id} не найден в базе")

            actual_dataset_id = int(row["dataset_id"])
            for change in items:
                claimed_dataset_id = int(change["dataset_id"])
                if claimed_dataset_id != actual_dataset_id:
                    raise ValueError(
                        f"Анализ {analysis_id} принадлежит dataset {actual_dataset_id}, "
                        f"а изменение заявлено для dataset {claimed_dataset_id}."
                    )

            data = json.loads(row["data_json"])
            for change in items:
                data[change["column_name"]] = change["new_value"]
                con.execute(
                    """
                    INSERT INTO change_log(
                        dataset_id, analysis_id, column_name, old_value, new_value,
                        synced_to_source, source_backup, changed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        actual_dataset_id,
                        analysis_id,
                        change["column_name"],
                        None if change.get("old_value") is None else str(change["old_value"]),
                        None if change.get("new_value") is None else str(change["new_value"]),
                        1 if synced_to_source else 0,
                        str(change.get("source_backup") or ""),
                        now,
                    ),
                )

            con.execute(
                "UPDATE analysis_rows SET data_json=?, updated_at=? WHERE analysis_id=?",
                (json.dumps(data, ensure_ascii=False), now, analysis_id),
            )

        con.commit()
