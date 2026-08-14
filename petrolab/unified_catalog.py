from __future__ import annotations

import json
from collections import defaultdict

import pandas as pd

from petrolab.db import connect
from petrolab.sample_registry import ensure_sample_registry_schema


def sample_overview(project_id: int | None = None) -> pd.DataFrame:
    """One row per canonical Sample with counts across every scientific domain."""
    ensure_sample_registry_schema()
    with connect() as con:
        where = "WHERE s.project_id=?" if project_id is not None else ""
        params = (int(project_id),) if project_id is not None else ()
        samples = con.execute(
            f"""
            SELECT s.id, s.project_id, p.name AS project, s.name, s.field_lithology,
                   s.locality, s.latitude, s.longitude
            FROM samples s JOIN projects p ON p.id=s.project_id
            {where}
            ORDER BY p.name, s.name COLLATE NOCASE
            """,
            params,
        ).fetchall()
        rows = []
        for sample in samples:
            sid = int(sample["id"])
            datasets = con.execute(
                "SELECT id, mineral_key, row_count FROM datasets WHERE sample_id=?",
                (sid,),
            ).fetchall()
            dataset_ids = [int(row["id"]) for row in datasets]
            mineral_counts: dict[str, int] = defaultdict(int)
            for row in datasets:
                mineral_counts[str(row["mineral_key"] or "unknown")] += int(row["row_count"] or 0)
            rock = con.execute("SELECT id FROM rock_samples WHERE sample_id=?", (sid,)).fetchall()
            rock_ids = [int(row["id"]) for row in rock]
            chemistry_count = 0
            isotope_count = 0
            if rock_ids:
                marks = ",".join("?" for _ in rock_ids)
                chemistry_count = int(con.execute(f"SELECT COUNT(*) FROM rock_compositions WHERE rock_id IN ({marks})", rock_ids).fetchone()[0])
                isotope_count = int(con.execute(f"SELECT COUNT(*) FROM rock_isotopes WHERE rock_id IN ({marks})", rock_ids).fetchone()[0])
            session_count = 0
            tables = {str(r[0]) for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            if "analytical_sessions" in tables:
                session_count = int(con.execute("SELECT COUNT(*) FROM analytical_sessions WHERE sample_id=?", (sid,)).fetchone()[0])
            aliases = [str(r[0]) for r in con.execute("SELECT alias FROM sample_aliases WHERE sample_id=? ORDER BY alias", (sid,)).fetchall()]
            rows.append({
                "sample_id": sid,
                "project_id": int(sample["project_id"]),
                "Проект": str(sample["project"]),
                "Образец": str(sample["name"]),
                "Aliases": ", ".join(aliases),
                "Полевое название": str(sample["field_lithology"] or ""),
                "Местность": str(sample["locality"] or ""),
                "Сессий": session_count,
                "Минеральных анализов": sum(mineral_counts.values()),
                "Минералы": ", ".join(f"{key}: {value}" for key, value in sorted(mineral_counts.items())),
                "Whole-rock параметров": chemistry_count,
                "Изотопных измерений": isotope_count,
                "Пустой": not dataset_ids and not rock_ids and session_count == 0,
            })
    return pd.DataFrame(rows)


def mineral_inventory(project_id: int | None = None) -> pd.DataFrame:
    """Counts of all mineral analyses, globally or by project."""
    ensure_sample_registry_schema()
    with connect() as con:
        clauses = []
        params: list[object] = []
        if project_id is not None:
            clauses.append("d.project_id=?")
            params.append(int(project_id))
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        rows = con.execute(
            f"""
            SELECT d.mineral_key AS mineral,
                   COUNT(DISTINCT d.id) AS datasets,
                   COUNT(DISTINCT d.sample_id) AS samples,
                   COUNT(DISTINCT d.project_id) AS projects,
                   COALESCE(SUM(d.row_count),0) AS analyses
            FROM datasets d
            {where}
            GROUP BY d.mineral_key
            ORDER BY analyses DESC, mineral
            """,
            params,
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def mineral_analysis_ids(mineral_key: str, project_id: int | None = None) -> list[str]:
    ensure_sample_registry_schema()
    with connect() as con:
        params: list[object] = [str(mineral_key)]
        extra = ""
        if project_id is not None:
            extra = " AND d.project_id=?"
            params.append(int(project_id))
        rows = con.execute(
            f"""
            SELECT a.analysis_id
            FROM analysis_rows a JOIN datasets d ON d.id=a.dataset_id
            WHERE d.mineral_key=? {extra}
            ORDER BY a.analysis_id
            """,
            params,
        ).fetchall()
    return [str(row[0]) for row in rows]


def whole_rock_inventory(project_id: int | None = None) -> pd.DataFrame:
    ensure_sample_registry_schema()
    with connect() as con:
        params: list[object] = []
        project_clause = ""
        if project_id is not None:
            project_clause = " AND r.project_id=?"
            params.append(int(project_id))
        rows = con.execute(
            f"""
            SELECT s.name AS sample, p.name AS project, r.id AS rock_id,
                   r.lithology, r.massif, r.locality,
                   COUNT(DISTINCT c.id) AS chemistry_values,
                   COUNT(DISTINCT i.id) AS isotope_values
            FROM rock_samples r
            JOIN projects p ON p.id=r.project_id
            LEFT JOIN samples s ON s.id=r.sample_id
            LEFT JOIN rock_compositions c ON c.rock_id=r.id
            LEFT JOIN rock_isotopes i ON i.rock_id=r.id
            WHERE 1=1 {project_clause}
            GROUP BY r.id
            ORDER BY p.name, COALESCE(s.name,r.name)
            """,
            params,
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def unlinked_rock_samples(project_id: int | None = None) -> pd.DataFrame:
    ensure_sample_registry_schema()
    with connect() as con:
        params: list[object] = []
        clause = ""
        if project_id is not None:
            clause = " AND r.project_id=?"
            params.append(int(project_id))
        rows = con.execute(
            f"""
            SELECT r.id AS rock_id, r.project_id, p.name AS project, r.name,
                   r.lithology, r.massif, r.locality
            FROM rock_samples r JOIN projects p ON p.id=r.project_id
            WHERE r.sample_id IS NULL {clause}
            ORDER BY p.name, r.name COLLATE NOCASE
            """,
            params,
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])
