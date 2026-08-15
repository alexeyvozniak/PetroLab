"""Composite physical points built from explicit EDS/EPMA/LA links.

Raw analytical rows are never merged or rewritten.  A composite point is a
read-only scientific view over several immutable ``analysis_id`` values tied to
one physical target.  This lets a user plot, for example, MgO from EPMA against
Rb from LA-ICP-MS while retaining method-level provenance for every value.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from petrolab.db import connect
from petrolab.derived import load_dataset_with_derived
from petrolab.measurement_registry import create_entity, ensure_measurement_registry_schema
from petrolab.slides import ensure_slide_schema, list_slide_markers


_META_COLUMNS = {
    "_analysis_id", "_dataset_id", "_project_id", "_row_index", "_source_row",
    "Проект", "Набор", "Минерал", "Источник", "Лист", "Строка Excel",
}
_IDENTITY_COLUMNS = {"Sample", "Grain", "Point", "Generation", "PetroLab Generation"}


@dataclass(frozen=True)
class CompositeLinkResult:
    entity_id: int
    linked_analysis_ids: tuple[str, ...]


def ensure_composite_schema() -> None:
    ensure_measurement_registry_schema()
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS physical_point_analysis_links (
                entity_id INTEGER NOT NULL,
                analysis_id TEXT NOT NULL,
                link_role TEXT NOT NULL DEFAULT '',
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(entity_id, analysis_id),
                FOREIGN KEY(entity_id) REFERENCES physical_entities(id) ON DELETE CASCADE,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE
            )"""
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_physical_point_analysis ON physical_point_analysis_links(analysis_id)"
        )
        con.commit()


def _validate_point(con, project_id: int, entity_id: int) -> None:
    row = con.execute(
        "SELECT project_id, kind FROM physical_entities WHERE id=?", (int(entity_id),)
    ).fetchone()
    if not row or int(row["project_id"]) != int(project_id):
        raise ValueError("Физическая точка не относится к этому проекту")
    if str(row["kind"]) not in {"probe_point", "la_crater"}:
        raise ValueError("Для composite analysis нужна аналитическая физическая точка")


def _validate_analysis(con, project_id: int, analysis_id: str) -> None:
    row = con.execute(
        """SELECT 1 FROM analysis_rows a
           JOIN project_dataset_links l ON l.dataset_id=a.dataset_id
           WHERE a.analysis_id=? AND l.project_id=?""",
        (str(analysis_id), int(project_id)),
    ).fetchone()
    if not row:
        raise ValueError("Анализ не входит в рабочий контекст проекта")


def set_physical_point_links(
    project_id: int,
    entity_id: int,
    analysis_ids: Iterable[str],
    *,
    link_role: str = "same_physical_position",
    note: str = "",
) -> CompositeLinkResult:
    """Replace links for one physical point after an explicit user decision."""
    ensure_composite_schema()
    ids = tuple(dict.fromkeys(str(value).strip() for value in analysis_ids if str(value).strip()))
    with connect() as con:
        _validate_point(con, int(project_id), int(entity_id))
        for analysis_id in ids:
            _validate_analysis(con, int(project_id), analysis_id)
        con.execute("DELETE FROM physical_point_analysis_links WHERE entity_id=?", (int(entity_id),))
        con.executemany(
            """INSERT INTO physical_point_analysis_links(entity_id,analysis_id,link_role,note)
               VALUES(?,?,?,?)""",
            [(int(entity_id), analysis_id, str(link_role), str(note)) for analysis_id in ids],
        )
        con.commit()
    return CompositeLinkResult(int(entity_id), ids)


def add_physical_point_links(
    project_id: int,
    entity_id: int,
    analysis_ids: Iterable[str],
    *,
    link_role: str = "same_physical_position",
    note: str = "",
) -> CompositeLinkResult:
    ensure_composite_schema()
    ids = tuple(dict.fromkeys(str(value).strip() for value in analysis_ids if str(value).strip()))
    with connect() as con:
        _validate_point(con, int(project_id), int(entity_id))
        for analysis_id in ids:
            _validate_analysis(con, int(project_id), analysis_id)
        con.executemany(
            """INSERT OR REPLACE INTO physical_point_analysis_links(entity_id,analysis_id,link_role,note)
               VALUES(?,?,?,?)""",
            [(int(entity_id), analysis_id, str(link_role), str(note)) for analysis_id in ids],
        )
        con.commit()
        rows = con.execute(
            "SELECT analysis_id FROM physical_point_analysis_links WHERE entity_id=? ORDER BY analysis_id",
            (int(entity_id),),
        ).fetchall()
    return CompositeLinkResult(int(entity_id), tuple(str(row["analysis_id"]) for row in rows))


def list_physical_points(project_id: int, *, thin_section_id: int | None = None) -> list[dict]:
    ensure_composite_schema()
    query = """
        SELECT e.*, s.name AS sample_name, parent.name AS thin_section_name,
               COUNT(l.analysis_id) AS linked_analyses
        FROM physical_entities e
        LEFT JOIN samples s ON s.id=e.sample_id
        LEFT JOIN physical_entities parent ON parent.id=e.parent_id
        LEFT JOIN physical_point_analysis_links l ON l.entity_id=e.id
        WHERE e.project_id=? AND e.kind IN ('probe_point','la_crater')
    """
    params: list[object] = [int(project_id)]
    if thin_section_id is not None:
        query += " AND e.parent_id=?"
        params.append(int(thin_section_id))
    query += " GROUP BY e.id ORDER BY COALESCE(parent.name,''), e.name COLLATE NOCASE, e.id"
    with connect() as con:
        rows = con.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def _find_or_create_marker_entity(project_id: int, marker: dict, thin_section_id: int, sample_id: int | None) -> int | None:
    label = str(marker.get("label") or marker.get("entity_name") or "").strip()
    if not label:
        return None
    existing_entity = marker.get("entity_id")
    if existing_entity is not None:
        return int(existing_entity)
    with connect() as con:
        row = con.execute(
            """SELECT id FROM physical_entities
               WHERE project_id=? AND parent_id=? AND kind='probe_point' AND name=?""",
            (int(project_id), int(thin_section_id), label),
        ).fetchone()
    if row:
        return int(row["id"])
    try:
        return create_entity(
            int(project_id), kind="probe_point", name=label,
            sample_id=sample_id, parent_id=int(thin_section_id),
            description="Создано из разметки шлифа для composite analysis",
        )
    except ValueError:
        with connect() as con:
            row = con.execute(
                """SELECT id FROM physical_entities
                   WHERE project_id=? AND parent_id=? AND kind='probe_point' AND name=?""",
                (int(project_id), int(thin_section_id), label),
            ).fetchone()
        return int(row["id"]) if row else None


def sync_slide_markers_to_physical_points(project_id: int) -> int:
    """Promote labelled slide markers into explicit physical points and copy their links.

    Matching is restricted to the same thin section and exact marker label.  The user still
    controls later EDS/LA linkage in the composite-point editor; no chemical values are merged.
    """
    ensure_composite_schema()
    ensure_slide_schema()
    with connect() as con:
        images = con.execute(
            """SELECT si.id, si.thin_section_id, e.sample_id
               FROM slide_images si LEFT JOIN physical_entities e ON e.id=si.thin_section_id
               WHERE si.project_id=? AND si.thin_section_id IS NOT NULL""",
            (int(project_id),),
        ).fetchall()
    image_info = {
        int(row["id"]): (int(row["thin_section_id"]), row["sample_id"])
        for row in images
    }
    changed = 0
    for marker in list_slide_markers(int(project_id)):
        info = image_info.get(int(marker["slide_image_id"]))
        if info is None:
            continue
        entity_id = _find_or_create_marker_entity(int(project_id), marker, info[0], info[1])
        if entity_id is None:
            continue
        analysis_ids = tuple(str(value) for value in marker.get("analysis_ids", []) if str(value).strip())
        if analysis_ids:
            add_physical_point_links(
                int(project_id), entity_id, analysis_ids,
                link_role="slide_marker", note=f"Маркер {marker.get('label') or marker['id']}",
            )
        with connect() as con:
            if marker.get("entity_id") is None:
                con.execute("UPDATE slide_markers SET entity_id=? WHERE id=?", (int(entity_id), int(marker["id"])))
                con.commit()
                changed += 1
    return changed


def _is_missing(value: object) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _same_value(a: object, b: object) -> bool:
    if _is_missing(a) and _is_missing(b):
        return True
    if _is_missing(a) or _is_missing(b):
        return False
    try:
        af, bf = float(a), float(b)
        if math.isfinite(af) and math.isfinite(bf):
            return math.isclose(af, bf, rel_tol=1e-9, abs_tol=1e-12)
    except (TypeError, ValueError):
        pass
    return str(a) == str(b)


def _safe_label(text: str) -> str:
    clean = " ".join(str(text or "").split())
    return clean[:80] or "analysis"


def _merge_records(records: list[dict]) -> tuple[dict, dict, list[str]]:
    """Merge non-conflicting fields and expose collisions as method-qualified columns."""
    contributions: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        values = dict(record["values"])
        for column, value in values.items():
            if str(column).startswith("_") or column in _META_COLUMNS:
                continue
            if _is_missing(value):
                continue
            contributions[str(column)].append({
                "analysis_id": record["analysis_id"],
                "dataset_id": record["dataset_id"],
                "dataset": record["dataset"],
                "source": record["source"],
                "value": value,
            })

    merged: dict[str, object] = {}
    provenance: dict[str, list[dict]] = {}
    conflicts: list[str] = []
    for column, items in contributions.items():
        unique: list[dict] = []
        for item in items:
            if not any(_same_value(item["value"], existing["value"]) for existing in unique):
                unique.append(item)
        if len(unique) == 1:
            merged[column] = unique[0]["value"]
            provenance[column] = items
            continue
        conflicts.append(column)
        merged[column] = pd.NA
        used: set[str] = set()
        for index, item in enumerate(items, 1):
            label = _safe_label(item["dataset"])
            qualified = f"{column} · {label}"
            if qualified in used:
                qualified = f"{qualified} · {index}"
            used.add(qualified)
            merged[qualified] = item["value"]
            provenance[qualified] = [item]
    return merged, provenance, conflicts


def composite_points_dataframe(project_id: int, *, thin_section_id: int | None = None) -> pd.DataFrame:
    """Return one row per explicit physical point with transparent value provenance."""
    ensure_composite_schema()
    sync_slide_markers_to_physical_points(int(project_id))
    points = list_physical_points(int(project_id), thin_section_id=thin_section_id)
    if not points:
        return pd.DataFrame()

    with connect() as con:
        links = con.execute(
            """SELECT l.entity_id, l.analysis_id, a.dataset_id, d.name AS dataset_name,
                      d.source_filename, d.mineral_key
               FROM physical_point_analysis_links l
               JOIN physical_entities e ON e.id=l.entity_id
               JOIN analysis_rows a ON a.analysis_id=l.analysis_id
               JOIN datasets d ON d.id=a.dataset_id
               WHERE e.project_id=?""",
            (int(project_id),),
        ).fetchall()
    links_by_point: dict[int, list[dict]] = defaultdict(list)
    dataset_ids: set[int] = set()
    for row in links:
        item = dict(row)
        links_by_point[int(item["entity_id"])].append(item)
        dataset_ids.add(int(item["dataset_id"]))

    analysis_frames: dict[int, pd.DataFrame] = {}
    for dataset_id in dataset_ids:
        frame = load_dataset_with_derived(int(dataset_id), include_meta=True)
        if not frame.empty and "_analysis_id" in frame.columns:
            analysis_frames[int(dataset_id)] = frame.set_index(frame["_analysis_id"].astype(str), drop=False)

    rows: list[dict] = []
    for point in points:
        point_links = links_by_point.get(int(point["id"]), [])
        records: list[dict] = []
        minerals: list[str] = []
        datasets: list[str] = []
        sources: list[str] = []
        ids: list[str] = []
        for link in point_links:
            dataset_id = int(link["dataset_id"])
            analysis_id = str(link["analysis_id"])
            frame = analysis_frames.get(dataset_id)
            if frame is None or analysis_id not in frame.index:
                continue
            series = frame.loc[analysis_id]
            if isinstance(series, pd.DataFrame):
                series = series.iloc[0]
            records.append({
                "analysis_id": analysis_id,
                "dataset_id": dataset_id,
                "dataset": str(link["dataset_name"]),
                "source": str(link["source_filename"]),
                "values": series.to_dict(),
            })
            ids.append(analysis_id)
            datasets.append(str(link["dataset_name"]))
            sources.append(str(link["source_filename"]))
            mineral = str(link.get("mineral_key") or "")
            if mineral and mineral != "generic":
                minerals.append(mineral)

        merged, provenance, conflicts = _merge_records(records)
        record = {
            "_physical_point_id": int(point["id"]),
            "_analysis_ids": " | ".join(dict.fromkeys(ids)),
            "_dataset_ids": " | ".join(str(value) for value in dict.fromkeys(int(link["dataset_id"]) for link in point_links)),
            "Physical Point": str(point["name"]),
            "Sample": str(point.get("sample_name") or ""),
            "Thin Section": str(point.get("thin_section_name") or ""),
            "Минерал": next(iter(dict.fromkeys(minerals)), "") if len(set(minerals)) <= 1 else "mixed",
            "Наборы": " | ".join(dict.fromkeys(datasets)),
            "Источник": " | ".join(dict.fromkeys(sources)),
            "Связанных анализов": len(ids),
            "Конфликты методов": ", ".join(conflicts),
            "_provenance_json": json.dumps(provenance, ensure_ascii=False, default=str),
            **merged,
        }
        rows.append(record)
    return pd.DataFrame(rows)


def composite_point_provenance(row: pd.Series | dict) -> dict:
    raw = row.get("_provenance_json", "{}") if hasattr(row, "get") else "{}"
    try:
        value = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}
