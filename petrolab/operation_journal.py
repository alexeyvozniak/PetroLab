from __future__ import annotations

import json
from collections import defaultdict
from typing import Iterable

from petrolab.analytical_sessions import annotation_table, ensure_session_schema, set_annotations
from petrolab.db import _utcnow, connect
from petrolab.generations import assign_generation, clear_generation, generation_map
from petrolab.phase_reassignment import reassign_confirmed_phase, restore_phase_reassignment


def _ids(values: Iterable[str]) -> list[str]:
    return sorted({str(value).strip() for value in values if str(value).strip()})


def ensure_operation_journal() -> None:
    ensure_session_schema()
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS interpretation_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                operation_kind TEXT NOT NULL,
                label TEXT NOT NULL,
                affected_count INTEGER NOT NULL DEFAULT 0,
                payload_json TEXT NOT NULL DEFAULT '{}',
                inverse_json TEXT NOT NULL DEFAULT '{}',
                can_undo INTEGER NOT NULL DEFAULT 1,
                undone_at TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_interpretation_ops_project ON interpretation_operations(project_id, id DESC)"
        )
        con.commit()


def record_operation(
    project_id: int,
    *,
    operation_kind: str,
    label: str,
    affected_count: int,
    payload: dict | None = None,
    inverse: dict | None = None,
    can_undo: bool = True,
) -> int:
    ensure_operation_journal()
    with connect() as con:
        cur = con.execute(
            """
            INSERT INTO interpretation_operations(
                project_id, operation_kind, label, affected_count, payload_json,
                inverse_json, can_undo, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(project_id), str(operation_kind).strip(), str(label).strip(), int(affected_count),
                json.dumps(payload or {}, ensure_ascii=False), json.dumps(inverse or {}, ensure_ascii=False),
                1 if can_undo else 0, _utcnow(),
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def list_operations(project_id: int, limit: int = 200) -> list[dict]:
    ensure_operation_journal()
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM interpretation_operations WHERE project_id=? ORDER BY id DESC LIMIT ?",
            (int(project_id), int(limit)),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for field in ("payload_json", "inverse_json"):
            try:
                item[field[:-5]] = json.loads(str(item.pop(field)))
            except (json.JSONDecodeError, TypeError):
                item[field[:-5]] = {}
        result.append(item)
    return result


def assign_generation_with_journal(
    project_id: int,
    analysis_ids: Iterable[str],
    generation_name: str,
    *,
    rationale: str = "",
) -> int:
    ids = _ids(analysis_ids)
    if not ids:
        return 0
    before = generation_map()
    previous = {analysis_id: before.get(analysis_id, "") for analysis_id in ids}
    count = assign_generation(
        ids, generation_name, rationale=rationale,
        source_kind="batch_manual", source_value="product_guidance",
    )
    record_operation(
        project_id,
        operation_kind="generation_assign",
        label=f"Generation → {str(generation_name).strip()}",
        affected_count=count,
        payload={"analysis_ids": ids, "generation": str(generation_name).strip(), "rationale": str(rationale).strip()},
        inverse={"previous": previous},
    )
    return count


def set_annotation_with_journal(
    project_id: int,
    analysis_ids: Iterable[str],
    *,
    namespace: str,
    key: str,
    value: str,
    label: str = "",
) -> int:
    ids = _ids(analysis_ids)
    clean_key = str(key).strip()
    clean_value = str(value).strip()
    if not ids or not clean_key or not clean_value:
        return 0
    before = annotation_table(ids, namespace=namespace)
    previous = {analysis_id: before.get(analysis_id, {}).get(clean_key, "") for analysis_id in ids}
    count = set_annotations(ids, {clean_key: clean_value}, namespace=namespace, source="batch_manual")
    record_operation(
        project_id,
        operation_kind="annotation_set",
        label=label or f"{namespace}.{clean_key} → {clean_value}",
        affected_count=count,
        payload={"analysis_ids": ids, "namespace": namespace, "key": clean_key, "value": clean_value},
        inverse={"previous": previous},
    )
    return count


def reassign_phase_with_journal(
    project_id: int,
    analysis_ids: Iterable[str],
    phase_label: str,
) -> int:
    ids = _ids(analysis_ids)
    if not ids:
        return 0
    snapshot = reassign_confirmed_phase(ids, phase_label)
    record_operation(
        project_id,
        operation_kind="phase_reassign",
        label=f"Фаза → {str(phase_label).strip()}",
        affected_count=len(ids),
        payload={"analysis_ids": ids, "phase": str(phase_label).strip()},
        inverse=snapshot,
    )
    return len(ids)


def _restore_annotations(namespace: str, key: str, previous: dict[str, str]) -> None:
    ensure_session_schema()
    with connect() as con:
        for analysis_id, value in previous.items():
            if str(value):
                con.execute(
                    """
                    INSERT INTO analysis_annotations(analysis_id, namespace, key, value, source, updated_at)
                    VALUES (?, ?, ?, ?, 'undo', CURRENT_TIMESTAMP)
                    ON CONFLICT(analysis_id, namespace, key) DO UPDATE SET
                        value=excluded.value, source='undo', updated_at=CURRENT_TIMESTAMP
                    """,
                    (str(analysis_id), str(namespace), str(key), str(value)),
                )
            else:
                con.execute(
                    "DELETE FROM analysis_annotations WHERE analysis_id=? AND namespace=? AND key=?",
                    (str(analysis_id), str(namespace), str(key)),
                )
        con.commit()


def _restore_generations(previous: dict[str, str]) -> None:
    grouped: dict[str, list[str]] = defaultdict(list)
    cleared: list[str] = []
    for analysis_id, value in previous.items():
        if str(value).strip():
            grouped[str(value)].append(str(analysis_id))
        else:
            cleared.append(str(analysis_id))
    if cleared:
        clear_generation(cleared, rationale="Undo массовой операции")
    for generation, ids in grouped.items():
        assign_generation(ids, generation, rationale="Undo массовой операции", source_kind="undo", source_value="operation_journal")


def undo_operation(project_id: int, operation_id: int) -> str:
    ensure_operation_journal()
    with connect() as con:
        row = con.execute(
            "SELECT * FROM interpretation_operations WHERE id=? AND project_id=?",
            (int(operation_id), int(project_id)),
        ).fetchone()
    if not row:
        raise ValueError("Операция не найдена")
    if not int(row["can_undo"]):
        raise ValueError("Эта операция только аудируется и не поддерживает автоматическую отмену")
    if str(row["undone_at"] or ""):
        raise ValueError("Операция уже отменена")
    try:
        payload = json.loads(str(row["payload_json"]))
        inverse = json.loads(str(row["inverse_json"]))
    except json.JSONDecodeError as exc:
        raise ValueError("Повреждён журнал операции") from exc

    kind = str(row["operation_kind"])
    if kind == "generation_assign":
        _restore_generations(dict(inverse.get("previous") or {}))
    elif kind == "annotation_set":
        _restore_annotations(
            str(payload.get("namespace") or "morphology"),
            str(payload.get("key") or ""),
            dict(inverse.get("previous") or {}),
        )
    elif kind == "phase_reassign":
        restore_phase_reassignment(inverse)
    else:
        raise ValueError("Для этого типа операции автоматическая отмена ещё не реализована")

    with connect() as con:
        con.execute(
            "UPDATE interpretation_operations SET undone_at=? WHERE id=?",
            (_utcnow(), int(operation_id)),
        )
        con.commit()
    return str(row["label"])
