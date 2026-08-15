from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from petrolab.db import connect


@dataclass(frozen=True)
class LinkedPhaseSuggestion:
    analysis_id: str
    phase_label: str
    evidence_analysis_ids: tuple[str, ...]
    reason: str
    conflict: bool = False


def _table_exists(con, name: str) -> bool:
    return bool(
        con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (str(name),),
        ).fetchone()
    )


def _linked_analysis_ids(con, project_id: int, analysis_id: str) -> set[str]:
    """Return analyses explicitly tied to the same physical location/entity."""
    linked: set[str] = set()

    if _table_exists(con, "physical_point_analysis_links"):
        rows = con.execute(
            """SELECT DISTINCT other.analysis_id
               FROM physical_point_analysis_links own
               JOIN physical_point_analysis_links other ON other.entity_id=own.entity_id
               JOIN physical_entities e ON e.id=own.entity_id
               JOIN analysis_rows ar ON ar.analysis_id=other.analysis_id
               JOIN project_dataset_links pdl ON pdl.dataset_id=ar.dataset_id
               WHERE own.analysis_id=? AND other.analysis_id<>?
                 AND e.project_id=? AND pdl.project_id=?""",
            (str(analysis_id), str(analysis_id), int(project_id), int(project_id)),
        ).fetchall()
        linked.update(str(row["analysis_id"]) for row in rows)

    if _table_exists(con, "slide_marker_analysis_links"):
        rows = con.execute(
            """SELECT DISTINCT other.analysis_id
               FROM slide_marker_analysis_links own
               JOIN slide_marker_analysis_links other ON other.marker_id=own.marker_id
               JOIN analysis_rows ar ON ar.analysis_id=other.analysis_id
               JOIN project_dataset_links pdl ON pdl.dataset_id=ar.dataset_id
               WHERE own.analysis_id=? AND other.analysis_id<>? AND pdl.project_id=?""",
            (str(analysis_id), str(analysis_id), int(project_id)),
        ).fetchall()
        linked.update(str(row["analysis_id"]) for row in rows)

    if _table_exists(con, "observations"):
        rows = con.execute(
            """SELECT DISTINCT other.analysis_id
               FROM observations own
               JOIN observations other ON other.entity_id=own.entity_id
               JOIN analysis_rows ar ON ar.analysis_id=other.analysis_id
               JOIN project_dataset_links pdl ON pdl.dataset_id=ar.dataset_id
               WHERE own.project_id=? AND own.analysis_id=? AND own.entity_id IS NOT NULL
                 AND other.analysis_id IS NOT NULL AND other.analysis_id<>? AND pdl.project_id=?""",
            (int(project_id), str(analysis_id), str(analysis_id), int(project_id)),
        ).fetchall()
        linked.update(str(row["analysis_id"]) for row in rows)

    return linked


def _is_automatic_source(source: str) -> bool:
    clean = str(source or "").strip().casefold()
    return clean.startswith("auto_") or clean.startswith("auto:") or clean.startswith("automatic")


def _phase_from_linked(con, linked_ids: set[str]) -> tuple[str, str, bool]:
    if not linked_ids:
        return "", "нет связанных аналитических строк с известной фазой", False
    marks = ",".join("?" for _ in linked_ids)

    # Exact human interpretation is strongest. Automatic high-confidence recognition is useful
    # evidence too, but it must never be described as a manual confirmation.
    if _table_exists(con, "analysis_annotations"):
        rows = con.execute(
            f"""SELECT analysis_id, value, source FROM analysis_annotations
                WHERE namespace='phase' AND key='confirmed_phase'
                  AND analysis_id IN ({marks}) AND TRIM(value)<>''""",
            list(linked_ids),
        ).fetchall()
        manual_labels = {
            str(row["value"]).strip()
            for row in rows
            if str(row["value"]).strip() and not _is_automatic_source(str(row["source"] or ""))
        }
        if len(manual_labels) == 1:
            return next(iter(manual_labels)), "та же физическая точка; фаза подтверждена исследователем у связанной строки", False
        if len(manual_labels) > 1:
            return "", "связанные анализы имеют разные ручные интерпретации фазы", True

        automatic_labels = {
            str(row["value"]).strip()
            for row in rows
            if str(row["value"]).strip() and _is_automatic_source(str(row["source"] or ""))
        }
        if len(automatic_labels) == 1:
            return next(iter(automatic_labels)), "та же физическая точка; фаза автоматически распознана у связанной строки", False
        if len(automatic_labels) > 1:
            return "", "автоматически распознанные связанные строки дают разные фазы", True

    rows = con.execute(
        f"""SELECT ar.analysis_id, d.mineral_key
            FROM analysis_rows ar JOIN datasets d ON d.id=ar.dataset_id
            WHERE ar.analysis_id IN ({marks})""",
        list(linked_ids),
    ).fetchall()
    labels = {
        str(row["mineral_key"]).strip()
        for row in rows
        if str(row["mineral_key"] or "").strip() not in {"", "generic"}
    }
    if len(labels) == 1:
        return next(iter(labels)), "та же физическая точка; минералогический модуль связанной строки", False
    if len(labels) > 1:
        return "", "связанные анализы относятся к разным минералогическим модулям", True
    return "", "у связанных строк фаза пока не подтверждена", False


def linked_phase_suggestions(
    project_id: int,
    analysis_ids: Iterable[str],
) -> dict[str, LinkedPhaseSuggestion]:
    """Suggest phase labels only from explicit physical links, never from name matching.

    This is intended for trace-only LA/solution data where chemical phase recognition is not
    defensible. EPMA/EDS/LA values remain separate measurements; only the mineral interpretation
    is reused when the same physical marker/entity explicitly connects their analysis IDs.
    Conflicting linked phases are returned as a conflict with an empty label.
    """
    ids = tuple(dict.fromkeys(str(value).strip() for value in analysis_ids if str(value).strip()))
    if not ids:
        return {}

    result: dict[str, LinkedPhaseSuggestion] = {}
    with connect() as con:
        for analysis_id in ids:
            linked = _linked_analysis_ids(con, int(project_id), analysis_id)
            if not linked:
                continue
            phase, reason, conflict = _phase_from_linked(con, linked)
            result[analysis_id] = LinkedPhaseSuggestion(
                analysis_id=analysis_id,
                phase_label=phase,
                evidence_analysis_ids=tuple(sorted(linked)),
                reason=reason,
                conflict=conflict,
            )
    return result
