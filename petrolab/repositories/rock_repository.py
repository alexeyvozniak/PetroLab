from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd

from petrolab.db import DB_PATH


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def create_rock(project_id: int, name: str, **metadata) -> int:
    now = _utcnow()
    fields = {
        "description": "", "massif": "", "locality": "", "lithology": "",
        "latitude": None, "longitude": None, "age_ma": None, "age_uncertainty_ma": None,
        "age_method": "", "chemistry_method": "", "isotope_method": "", "laboratory": "", "notes": "",
    }
    fields.update({key: value for key, value in metadata.items() if key in fields})
    with _connect() as con:
        cur = con.execute(
            """
            INSERT INTO rock_samples(
                project_id, name, description, massif, locality, lithology, latitude, longitude,
                age_ma, age_uncertainty_ma, age_method, chemistry_method, isotope_method,
                laboratory, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (project_id, name, fields["description"], fields["massif"], fields["locality"], fields["lithology"],
             fields["latitude"], fields["longitude"], fields["age_ma"], fields["age_uncertainty_ma"],
             fields["age_method"], fields["chemistry_method"], fields["isotope_method"], fields["laboratory"],
             fields["notes"], now, now),
        )
        return int(cur.lastrowid)


def update_rock(rock_id: int, **metadata) -> None:
    allowed = {
        "name", "description", "massif", "locality", "lithology", "latitude", "longitude",
        "age_ma", "age_uncertainty_ma", "age_method", "chemistry_method", "isotope_method",
        "laboratory", "notes",
    }
    values = {key: value for key, value in metadata.items() if key in allowed}
    if not values:
        return
    values["updated_at"] = _utcnow()
    assignments = ", ".join(f"{key}=?" for key in values)
    with _connect() as con:
        con.execute(f"UPDATE rock_samples SET {assignments} WHERE id=?", (*values.values(), int(rock_id)))


def delete_rock(rock_id: int) -> None:
    with _connect() as con:
        con.execute("DELETE FROM rock_samples WHERE id=?", (int(rock_id),))


def list_rocks(project_id: int | None = None) -> list[dict]:
    with _connect() as con:
        if project_id is None:
            rows = con.execute(
                "SELECT r.*, p.name AS project_name FROM rock_samples r JOIN projects p ON p.id=r.project_id ORDER BY p.name, r.name"
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT r.*, p.name AS project_name FROM rock_samples r JOIN projects p ON p.id=r.project_id WHERE r.project_id=? ORDER BY r.name",
                (int(project_id),),
            ).fetchall()
    return [dict(row) for row in rows]


def get_rock(rock_id: int) -> dict | None:
    with _connect() as con:
        row = con.execute(
            "SELECT r.*, p.name AS project_name FROM rock_samples r JOIN projects p ON p.id=r.project_id WHERE r.id=?",
            (int(rock_id),),
        ).fetchone()
    return dict(row) if row else None


def replace_composition(rock_id: int, composition: dict[str, float], *, units: dict[str, str] | None = None, method: str = "", source: str = "") -> None:
    units = units or {}
    now = _utcnow()
    with _connect() as con:
        con.execute("DELETE FROM rock_compositions WHERE rock_id=?", (int(rock_id),))
        for analyte, value in composition.items():
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            if pd.isna(numeric):
                continue
            con.execute(
                "INSERT INTO rock_compositions(rock_id, analyte, value, unit, method, source, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (int(rock_id), str(analyte), numeric, units.get(str(analyte), ""), method, source, now),
            )


def upsert_composition_values(rock_id: int, rows: Iterable[dict]) -> None:
    now = _utcnow()
    with _connect() as con:
        for row in rows:
            analyte = str(row.get("analyte", "")).strip()
            if not analyte:
                continue
            value = row.get("value")
            numeric = None if value in (None, "") else float(value)
            con.execute(
                """
                INSERT INTO rock_compositions(rock_id, analyte, value, unit, method, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rock_id, analyte) DO UPDATE SET
                    value=excluded.value, unit=excluded.unit, method=excluded.method,
                    source=excluded.source, updated_at=excluded.updated_at
                """,
                (int(rock_id), analyte, numeric, str(row.get("unit", "")), str(row.get("method", "")),
                 str(row.get("source", "")), now),
            )


def get_composition(rock_id: int) -> pd.DataFrame:
    with _connect() as con:
        rows = con.execute(
            "SELECT analyte, value, unit, method, source, updated_at FROM rock_compositions WHERE rock_id=? ORDER BY analyte",
            (int(rock_id),),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def composition_wide(project_id: int | None = None) -> pd.DataFrame:
    rocks = list_rocks(project_id)
    records: list[dict] = []
    for rock in rocks:
        record = {
            "_rock_id": rock["id"], "Project": rock["project_name"], "Rock": rock["name"],
            "Massif": rock["massif"], "Locality": rock["locality"], "Lithology": rock["lithology"],
            "Age_Ma": rock["age_ma"], "Age_uncertainty_Ma": rock["age_uncertainty_ma"],
        }
        comp = get_composition(int(rock["id"]))
        for _, row in comp.iterrows():
            record[str(row["analyte"])] = row["value"]
        records.append(record)
    return pd.DataFrame(records)


def replace_isotopes(rock_id: int, dataframe: pd.DataFrame) -> None:
    now = _utcnow()
    with _connect() as con:
        con.execute("DELETE FROM rock_isotopes WHERE rock_id=?", (int(rock_id),))
        for _, row in dataframe.iterrows():
            ratio = str(row.get("ratio_name", "")).strip()
            if not ratio:
                continue
            def number(key: str):
                value = row.get(key)
                if value in (None, "") or pd.isna(value):
                    return None
                return float(value)
            con.execute(
                """
                INSERT INTO rock_isotopes(
                    rock_id, system, ratio_name, value, uncertainty, initial_value, age_ma_used,
                    method, laboratory, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (int(rock_id), str(row.get("system", "")), ratio, number("value"), number("uncertainty"),
                 number("initial_value"), number("age_ma_used"), str(row.get("method", "")),
                 str(row.get("laboratory", "")), str(row.get("notes", "")), now),
            )


def get_isotopes(rock_id: int) -> pd.DataFrame:
    with _connect() as con:
        rows = con.execute(
            "SELECT system, ratio_name, value, uncertainty, initial_value, age_ma_used, method, laboratory, notes FROM rock_isotopes WHERE rock_id=? ORDER BY system, ratio_name",
            (int(rock_id),),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def isotope_wide(project_id: int | None = None) -> pd.DataFrame:
    records: list[dict] = []
    for rock in list_rocks(project_id):
        record = {"_rock_id": rock["id"], "Project": rock["project_name"], "Rock": rock["name"], "Age_Ma": rock["age_ma"]}
        isotopes = get_isotopes(int(rock["id"]))
        for _, row in isotopes.iterrows():
            if pd.notna(row["value"]):
                record[str(row["ratio_name"])] = row["value"]
            if pd.notna(row["initial_value"]):
                record[f"{row['ratio_name']}_initial"] = row["initial_value"]
        records.append(record)
    return pd.DataFrame(records)


def set_mineral_links(rock_id: int, dataset_ids: Iterable[int]) -> None:
    ids = sorted({int(value) for value in dataset_ids})
    with _connect() as con:
        con.execute("DELETE FROM rock_mineral_links WHERE rock_id=?", (int(rock_id),))
        now = _utcnow()
        for dataset_id in ids:
            con.execute(
                "INSERT INTO rock_mineral_links(rock_id, dataset_id, created_at) VALUES (?, ?, ?)",
                (int(rock_id), dataset_id, now),
            )


def list_mineral_links(rock_id: int) -> list[int]:
    with _connect() as con:
        rows = con.execute("SELECT dataset_id FROM rock_mineral_links WHERE rock_id=? ORDER BY dataset_id", (int(rock_id),)).fetchall()
    return [int(row[0]) for row in rows]
