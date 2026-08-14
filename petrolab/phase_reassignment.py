from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from petrolab.analytical_sessions import annotation_table, ensure_session_schema
from petrolab.db import _utcnow, connect
from petrolab.phase_suggestions import (
    _MIXED_SUFFIX,
    _RESOLVED_SUFFIX,
    _copy_dataset_context,
    _existing_phase_dataset,
    _move_rows_to_dataset,
    _record_confirmed_phases,
    _reindex_dataset_rows,
    _root_dataset_name,
    mineral_key_for_phase,
)


def _clean_ids(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def _source_root(con, dataset) -> object:
    rows = con.execute(
        """SELECT * FROM datasets
           WHERE project_id=? AND source_filename=? AND source_sheet=? AND source_sha256=?
           ORDER BY id""",
        (
            int(dataset["project_id"]), str(dataset["source_filename"]),
            str(dataset["source_sheet"]), str(dataset["source_sha256"]),
        ),
    ).fetchall()
    if not rows:
        return dataset
    for row in rows:
        name = str(row["name"])
        if name.endswith(_MIXED_SUFFIX) or name.endswith(_RESOLVED_SUFFIX):
            return row
    return rows[0]


def _ensure_phase_child(con, root, phase_label: str) -> int:
    root_name = _root_dataset_name(str(root["name"]))
    child_name = f"{root_name} · {phase_label}"
    child_id = _existing_phase_dataset(con, root, child_name)
    if child_id is not None:
        return int(child_id)
    columns = [str(row[1]) for row in con.execute("PRAGMA table_info(datasets)").fetchall() if str(row[1]) != "id"]
    values = {column: root[column] for column in columns}
    values["name"] = child_name
    values["mineral_key"] = mineral_key_for_phase(phase_label)
    values["row_count"] = 0
    values["imported_at"] = _utcnow()
    placeholders = ",".join("?" for _ in columns)
    cur = con.execute(
        f"INSERT INTO datasets({','.join(columns)}) VALUES ({placeholders})",
        [values[column] for column in columns],
    )
    child_id = int(cur.lastrowid)
    _copy_dataset_context(con, int(root["id"]), child_id)
    return child_id


def reassign_confirmed_phase(analysis_ids: Iterable[str], phase_label: str) -> dict:
    """Move analyses to the requested phase child and return an undo snapshot."""
    ensure_session_schema()
    ids = _clean_ids(analysis_ids)
    phase = str(phase_label).strip()
    if not ids:
        raise ValueError("Не выбраны анализы")
    if not phase:
        raise ValueError("Укажите фазу")
    previous_phase_table = annotation_table(ids, namespace="phase")
    previous_phase = {analysis_id: previous_phase_table.get(analysis_id, {}).get("confirmed_phase", "") for analysis_id in ids}
    snapshot_rows: list[dict] = []

    with connect() as con:
        marks = ",".join("?" for _ in ids)
        rows = con.execute(
            f"""SELECT a.analysis_id, a.dataset_id, d.*
                FROM analysis_rows a JOIN datasets d ON d.id=a.dataset_id
                WHERE a.analysis_id IN ({marks})""",
            ids,
        ).fetchall()
        found = {str(row["analysis_id"]) for row in rows}
        missing = [value for value in ids if value not in found]
        if missing:
            raise ValueError(f"Не найдены анализы: {len(missing)}")

        grouped: dict[int, list[str]] = defaultdict(list)
        dataset_rows: dict[int, object] = {}
        for row in rows:
            dataset_id = int(row["dataset_id"])
            grouped[dataset_id].append(str(row["analysis_id"]))
            dataset_rows[dataset_id] = row
            snapshot_rows.append({
                "analysis_id": str(row["analysis_id"]),
                "dataset_id": dataset_id,
                "phase": previous_phase.get(str(row["analysis_id"]), ""),
            })

        touched: set[int] = set()
        target_by_root: dict[int, int] = {}
        for source_dataset_id, source_ids in grouped.items():
            source = dataset_rows[source_dataset_id]
            root = _source_root(con, source)
            root_id = int(root["id"])
            target_id = target_by_root.get(root_id)
            if target_id is None:
                target_id = _ensure_phase_child(con, root, phase)
                target_by_root[root_id] = target_id
            if int(source_dataset_id) != int(target_id):
                _move_rows_to_dataset(con, int(source_dataset_id), int(target_id), source_ids)
                touched.update({int(source_dataset_id), int(target_id)})

        _record_confirmed_phases(con, {analysis_id: phase for analysis_id in ids})
        for dataset_id in touched:
            _reindex_dataset_rows(con, dataset_id)
        for root_id in target_by_root:
            remaining = _reindex_dataset_rows(con, root_id)
            root = con.execute("SELECT name FROM datasets WHERE id=?", (root_id,)).fetchone()
            if root:
                base = _root_dataset_name(str(root["name"]))
                con.execute(
                    "UPDATE datasets SET name=? WHERE id=?",
                    (f"{base}{_MIXED_SUFFIX}" if remaining else f"{base}{_RESOLVED_SUFFIX}", root_id),
                )
        con.commit()

    return {"rows": snapshot_rows, "new_phase": phase}


def restore_phase_reassignment(snapshot: dict) -> int:
    """Restore dataset membership and confirmed phase from a prior reassignment snapshot."""
    ensure_session_schema()
    rows = list(snapshot.get("rows") or [])
    if not rows:
        return 0
    with connect() as con:
        touched: set[int] = set()
        for index, item in enumerate(rows):
            analysis_id = str(item["analysis_id"])
            previous_dataset = int(item["dataset_id"])
            current = con.execute("SELECT dataset_id FROM analysis_rows WHERE analysis_id=?", (analysis_id,)).fetchone()
            if current is None:
                continue
            current_dataset = int(current["dataset_id"])
            if current_dataset != previous_dataset:
                # Unique temporary indices prevent collisions while several rows return to one dataset.
                temp = -2_000_000_000 - index
                con.execute(
                    "UPDATE analysis_rows SET dataset_id=?, row_index=? WHERE analysis_id=?",
                    (previous_dataset, temp, analysis_id),
                )
                touched.update({current_dataset, previous_dataset})
            previous_phase = str(item.get("phase") or "")
            if previous_phase:
                con.execute(
                    """INSERT INTO analysis_annotations(analysis_id, namespace, key, value, source, updated_at)
                       VALUES (?, 'phase', 'confirmed_phase', ?, 'undo', CURRENT_TIMESTAMP)
                       ON CONFLICT(analysis_id, namespace, key) DO UPDATE SET
                         value=excluded.value, source='undo', updated_at=CURRENT_TIMESTAMP""",
                    (analysis_id, previous_phase),
                )
            else:
                con.execute(
                    "DELETE FROM analysis_annotations WHERE analysis_id=? AND namespace='phase' AND key='confirmed_phase'",
                    (analysis_id,),
                )
        for dataset_id in touched:
            _reindex_dataset_rows(con, dataset_id)
        con.commit()
    return len(rows)
