"""Physical analytical targets and method-specific observations.

The registry deliberately complements ``analysis_rows``. A probe point, an
LA-ICP-MS crater and a TIMS aliquot are not interchangeable observations, even
when they all report titanium for the same grain.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Literal

from petrolab.db import connect


EntityKind = Literal["thin_section", "grain", "probe_point", "la_crater", "aliquot"]
_ENTITY_KINDS = {"thin_section", "grain", "probe_point", "la_crater", "aliquot"}


@dataclass(frozen=True)
class Observation:
    id: int
    entity_id: int | None
    analysis_id: str | None
    dataset_id: int | None
    session_id: int | None
    analyte: str
    reported_form: str
    value: float | None
    qualifier: str
    unit: str
    uncertainty: float | None
    method: str
    instrument: str
    standard_name: str
    source_note: str


def ensure_measurement_registry_schema() -> None:
    """Create the additive measurement registry only when the feature is used."""
    # Canonical Sample and analytical-session tables are dependencies of the registry.
    # They are initialized lazily here rather than from global storage bootstrap so that
    # ordinary app startup does not open extra SQLite connections on Windows.
    from petrolab.sample_registry import ensure_sample_registry_schema
    from petrolab.analytical_sessions import ensure_session_schema

    ensure_sample_registry_schema()
    ensure_session_schema()
    with connect() as con:
        con.execute(
            """CREATE TABLE IF NOT EXISTS physical_entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                sample_id INTEGER,
                parent_id INTEGER,
                kind TEXT NOT NULL,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, parent_id, kind, name),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(sample_id) REFERENCES samples(id) ON DELETE SET NULL,
                FOREIGN KEY(parent_id) REFERENCES physical_entities(id) ON DELETE CASCADE
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_entities_project ON physical_entities(project_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_entities_sample ON physical_entities(sample_id)")
        con.execute(
            """CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                entity_id INTEGER,
                analysis_id TEXT,
                dataset_id INTEGER,
                session_id INTEGER,
                analyte TEXT NOT NULL,
                reported_form TEXT NOT NULL DEFAULT '',
                value REAL,
                qualifier TEXT NOT NULL DEFAULT '',
                unit TEXT NOT NULL DEFAULT '',
                uncertainty REAL,
                method TEXT NOT NULL DEFAULT '',
                instrument TEXT NOT NULL DEFAULT '',
                standard_name TEXT NOT NULL DEFAULT '',
                source_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(entity_id) REFERENCES physical_entities(id) ON DELETE SET NULL,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE SET NULL,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE SET NULL,
                FOREIGN KEY(session_id) REFERENCES analytical_sessions(id) ON DELETE SET NULL
            )"""
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_observations_entity ON observations(entity_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_observations_analysis ON observations(analysis_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_observations_dataset ON observations(dataset_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_observations_session ON observations(session_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_observations_analyte ON observations(project_id, analyte)")
        con.commit()


def create_entity(
    project_id: int,
    *,
    kind: EntityKind,
    name: str,
    sample_id: int | None = None,
    parent_id: int | None = None,
    description: str = "",
) -> int:
    ensure_measurement_registry_schema()
    if kind not in _ENTITY_KINDS:
        raise ValueError("Неизвестный тип физической сущности")
    name = str(name).strip()
    if not name:
        raise ValueError("Укажите название сущности")
    with connect() as con:
        if not con.execute("SELECT 1 FROM projects WHERE id=?", (int(project_id),)).fetchone():
            raise ValueError("Проект не найден")
        if sample_id is not None:
            row = con.execute("SELECT project_id FROM samples WHERE id=?", (int(sample_id),)).fetchone()
            if not row or int(row["project_id"]) != int(project_id):
                raise ValueError("Образец не относится к этому проекту")
        if parent_id is not None:
            row = con.execute(
                "SELECT project_id, sample_id FROM physical_entities WHERE id=?", (int(parent_id),)
            ).fetchone()
            if not row or int(row["project_id"]) != int(project_id):
                raise ValueError("Родительская сущность не относится к этому проекту")
            parent_sample = row["sample_id"]
            if sample_id is not None and parent_sample is not None and int(parent_sample) != int(sample_id):
                raise ValueError("Дочерняя сущность не может относиться к другому Sample")
            if sample_id is None and parent_sample is not None:
                sample_id = int(parent_sample)
        cur = con.execute(
            "INSERT INTO physical_entities(project_id,sample_id,parent_id,kind,name,description) VALUES(?,?,?,?,?,?)",
            (int(project_id), sample_id, parent_id, kind, name, str(description).strip()),
        )
        con.commit()
        return int(cur.lastrowid)


def list_entities(project_id: int, *, sample_id: int | None = None) -> list[dict]:
    """Return physical targets with their sample and immediate parent labels."""
    ensure_measurement_registry_schema()
    query = """
        SELECT e.*, s.name AS sample_name, parent.name AS parent_name
        FROM physical_entities e
        LEFT JOIN samples s ON s.id=e.sample_id
        LEFT JOIN physical_entities parent ON parent.id=e.parent_id
        WHERE e.project_id=?
    """
    params: list[object] = [int(project_id)]
    if sample_id is not None:
        query += " AND e.sample_id=?"
        params.append(int(sample_id))
    query += " ORDER BY COALESCE(s.name, ''), e.created_at, e.id"
    with connect() as con:
        rows = con.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def _finite_optional(value: float | None, field: str) -> float | None:
    if value is None:
        return None
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{field} должно быть конечным числом")
    return numeric


def _validate_reference_project(con, project_id: int, *, entity_id=None, analysis_id=None, dataset_id=None, session_id=None) -> None:
    if entity_id is not None:
        row = con.execute("SELECT project_id FROM physical_entities WHERE id=?", (int(entity_id),)).fetchone()
        if not row or int(row["project_id"]) != int(project_id):
            raise ValueError("Сущность не относится к этому проекту")
    if dataset_id is not None:
        row = con.execute("SELECT project_id FROM datasets WHERE id=?", (int(dataset_id),)).fetchone()
        if not row or int(row["project_id"]) != int(project_id):
            raise ValueError("Dataset не относится к этому проекту")
    if analysis_id is not None:
        row = con.execute(
            """SELECT d.project_id, a.dataset_id
               FROM analysis_rows a JOIN datasets d ON d.id=a.dataset_id
               WHERE a.analysis_id=?""",
            (str(analysis_id),),
        ).fetchone()
        if not row or int(row["project_id"]) != int(project_id):
            raise ValueError("Анализ не относится к этому проекту")
        if dataset_id is not None and int(row["dataset_id"]) != int(dataset_id):
            raise ValueError("analysis_id не принадлежит указанному dataset")
    if session_id is not None:
        row = con.execute("SELECT project_id FROM analytical_sessions WHERE id=?", (int(session_id),)).fetchone()
        if not row or int(row["project_id"]) != int(project_id):
            raise ValueError("Аналитическая сессия не относится к этому проекту")


def add_observation(
    project_id: int,
    *,
    analyte: str,
    value: float | None,
    unit: str,
    method: str,
    reported_form: str = "",
    qualifier: str = "",
    uncertainty: float | None = None,
    entity_id: int | None = None,
    analysis_id: str | None = None,
    dataset_id: int | None = None,
    session_id: int | None = None,
    instrument: str = "",
    standard_name: str = "",
    source_note: str = "",
) -> Observation:
    ensure_measurement_registry_schema()
    analyte = str(analyte).strip()
    unit = str(unit).strip()
    method = str(method).strip()
    qualifier = str(qualifier).strip()
    if not analyte or not unit or not method:
        raise ValueError("Для измерения обязательны аналит, единица и метод")
    numeric_value = _finite_optional(value, "Значение")
    numeric_uncertainty = _finite_optional(uncertainty, "Неопределённость")
    if numeric_uncertainty is not None and numeric_uncertainty < 0:
        raise ValueError("Неопределённость не может быть отрицательной")
    if numeric_value is None and not qualifier:
        raise ValueError("Укажите числовое значение или qualifier")

    with connect() as con:
        if not con.execute("SELECT 1 FROM projects WHERE id=?", (int(project_id),)).fetchone():
            raise ValueError("Проект не найден")
        _validate_reference_project(
            con,
            int(project_id),
            entity_id=entity_id,
            analysis_id=analysis_id,
            dataset_id=dataset_id,
            session_id=session_id,
        )
        cur = con.execute(
            """INSERT INTO observations(
                   project_id,entity_id,analysis_id,dataset_id,session_id,analyte,reported_form,
                   value,qualifier,unit,uncertainty,method,instrument,standard_name,source_note
               ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                int(project_id), entity_id, analysis_id, dataset_id, session_id, analyte,
                str(reported_form).strip(), numeric_value, qualifier, unit, numeric_uncertainty,
                method, str(instrument).strip(), str(standard_name).strip(), str(source_note).strip(),
            ),
        )
        con.commit()
        return Observation(
            id=int(cur.lastrowid),
            entity_id=entity_id,
            analysis_id=analysis_id,
            dataset_id=dataset_id,
            session_id=session_id,
            analyte=analyte,
            reported_form=str(reported_form).strip(),
            value=numeric_value,
            qualifier=qualifier,
            unit=unit,
            uncertainty=numeric_uncertainty,
            method=method,
            instrument=str(instrument).strip(),
            standard_name=str(standard_name).strip(),
            source_note=str(source_note).strip(),
        )


def list_observations(
    project_id: int,
    *,
    entity_id: int | None = None,
    analysis_id: str | None = None,
    analyte: str | None = None,
) -> list[Observation]:
    """Return observations without collapsing repeated methods or reported forms."""
    ensure_measurement_registry_schema()
    clauses = ["project_id=?"]
    params: list[object] = [int(project_id)]
    if entity_id is not None:
        clauses.append("entity_id=?")
        params.append(int(entity_id))
    if analysis_id is not None:
        clauses.append("analysis_id=?")
        params.append(str(analysis_id))
    if analyte is not None:
        clauses.append("analyte=?")
        params.append(str(analyte).strip())
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM observations WHERE " + " AND ".join(clauses) + " ORDER BY id",
            params,
        ).fetchall()
    return [
        Observation(
            id=int(row["id"]), entity_id=row["entity_id"], analysis_id=row["analysis_id"],
            dataset_id=row["dataset_id"], session_id=row["session_id"], analyte=str(row["analyte"]),
            reported_form=str(row["reported_form"]), value=row["value"], qualifier=str(row["qualifier"]),
            unit=str(row["unit"]), uncertainty=row["uncertainty"], method=str(row["method"]),
            instrument=str(row["instrument"]), standard_name=str(row["standard_name"]),
            source_note=str(row["source_note"]),
        )
        for row in rows
    ]
