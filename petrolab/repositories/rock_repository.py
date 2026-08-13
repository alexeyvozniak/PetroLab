from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Iterator

import pandas as pd

from petrolab.db import DB_PATH


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def rock_connection() -> Iterator[sqlite3.Connection]:
    """Open one rock repository connection and always close it on Windows."""
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _nullable_float(value) -> float | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and not value.strip():
        return None
    return float(value)


def _text(value) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def create_rock(project_id: int, name: str, **metadata) -> int:
    clean_name = str(name).strip()
    if not clean_name:
        raise ValueError("Название породы не может быть пустым")
    now = _utcnow()
    fields = {
        "description": "", "massif": "", "locality": "", "lithology": "",
        "latitude": None, "longitude": None, "age_ma": None, "age_uncertainty_ma": None,
        "age_method": "", "chemistry_method": "", "isotope_method": "", "laboratory": "", "notes": "",
    }
    fields.update({key: value for key, value in metadata.items() if key in fields})
    with rock_connection() as con:
        cur = con.execute(
            """
            INSERT INTO rock_samples(
                project_id, name, description, massif, locality, lithology, latitude, longitude,
                age_ma, age_uncertainty_ma, age_method, chemistry_method, isotope_method,
                laboratory, notes, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(project_id), clean_name, _text(fields["description"]), _text(fields["massif"]),
                _text(fields["locality"]), _text(fields["lithology"]), _nullable_float(fields["latitude"]),
                _nullable_float(fields["longitude"]), _nullable_float(fields["age_ma"]),
                _nullable_float(fields["age_uncertainty_ma"]), _text(fields["age_method"]),
                _text(fields["chemistry_method"]), _text(fields["isotope_method"]),
                _text(fields["laboratory"]), _text(fields["notes"]), now, now,
            ),
        )
        return int(cur.lastrowid)


def update_rock(rock_id: int, **metadata) -> None:
    allowed = {
        "name", "description", "massif", "locality", "lithology", "latitude", "longitude",
        "age_ma", "age_uncertainty_ma", "age_method", "chemistry_method", "isotope_method",
        "laboratory", "notes",
    }
    numeric_fields = {"latitude", "longitude", "age_ma", "age_uncertainty_ma"}
    values: dict[str, object] = {}
    for key, value in metadata.items():
        if key not in allowed:
            continue
        values[key] = _nullable_float(value) if key in numeric_fields else _text(value)
    if "name" in values and not str(values["name"]).strip():
        raise ValueError("Название породы не может быть пустым")
    if not values:
        return
    values["updated_at"] = _utcnow()
    assignments = ", ".join(f"{key}=?" for key in values)
    with rock_connection() as con:
        con.execute(f"UPDATE rock_samples SET {assignments} WHERE id=?", (*values.values(), int(rock_id)))


def delete_rock(rock_id: int) -> None:
    with rock_connection() as con:
        con.execute("DELETE FROM rock_samples WHERE id=?", (int(rock_id),))


def list_rocks(project_id: int | None = None) -> list[dict]:
    with rock_connection() as con:
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
    with rock_connection() as con:
        row = con.execute(
            "SELECT r.*, p.name AS project_name FROM rock_samples r JOIN projects p ON p.id=r.project_id WHERE r.id=?",
            (int(rock_id),),
        ).fetchone()
    return dict(row) if row else None


def replace_composition(
    rock_id: int,
    composition: dict[str, float],
    *,
    units: dict[str, str] | None = None,
    method: str = "",
    source: str = "",
) -> None:
    units = units or {}
    now = _utcnow()
    with rock_connection() as con:
        con.execute("DELETE FROM rock_compositions WHERE rock_id=?", (int(rock_id),))
        for analyte, value in composition.items():
            numeric = _nullable_float(value)
            if numeric is None:
                continue
            con.execute(
                "INSERT INTO rock_compositions(rock_id, analyte, value, unit, method, source, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (int(rock_id), str(analyte), numeric, units.get(str(analyte), ""), method, source, now),
            )


def upsert_composition_values(rock_id: int, rows: Iterable[dict]) -> None:
    now = _utcnow()
    with rock_connection() as con:
        for row in rows:
            analyte = _text(row.get("analyte")).strip()
            if not analyte:
                continue
            numeric = _nullable_float(row.get("value"))
            con.execute(
                """
                INSERT INTO rock_compositions(rock_id, analyte, value, unit, method, source, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rock_id, analyte) DO UPDATE SET
                    value=excluded.value, unit=excluded.unit, method=excluded.method,
                    source=excluded.source, updated_at=excluded.updated_at
                """,
                (
                    int(rock_id), analyte, numeric, _text(row.get("unit")), _text(row.get("method")),
                    _text(row.get("source")), now,
                ),
            )


def get_composition(rock_id: int) -> pd.DataFrame:
    with rock_connection() as con:
        rows = con.execute(
            "SELECT analyte, value, unit, method, source, updated_at FROM rock_compositions WHERE rock_id=? ORDER BY analyte",
            (int(rock_id),),
        ).fetchall()
    return pd.DataFrame([dict(row) for row in rows])


def composition_wide(project_id: int | None = None) -> pd.DataFrame:
    records: list[dict] = []
    for rock in list_rocks(project_id):
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
    with rock_connection() as con:
        con.execute("DELETE FROM rock_isotopes WHERE rock_id=?", (int(rock_id),))
        for _, row in dataframe.iterrows():
            ratio = _text(row.get("ratio_name")).strip()
            if not ratio:
                continue
            con.execute(
                """
                INSERT INTO rock_isotopes(
                    rock_id, system, ratio_name, value, uncertainty, initial_value, age_ma_used,
                    method, laboratory, notes, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(rock_id), _text(row.get("system")), ratio, _nullable_float(row.get("value")),
                    _nullable_float(row.get("uncertainty")), _nullable_float(row.get("initial_value")),
                    _nullable_float(row.get("age_ma_used")), _text(row.get("method")),
                    _text(row.get("laboratory")), _text(row.get("notes")), now,
                ),
            )


def get_isotopes(rock_id: int) -> pd.DataFrame:
    with rock_connection() as con:
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
    with rock_connection() as con:
        con.execute("DELETE FROM rock_mineral_links WHERE rock_id=?", (int(rock_id),))
        now = _utcnow()
        for dataset_id in ids:
            con.execute(
                "INSERT INTO rock_mineral_links(rock_id, dataset_id, created_at) VALUES (?, ?, ?)",
                (int(rock_id), dataset_id, now),
            )


def list_mineral_links(rock_id: int) -> list[int]:
    with rock_connection() as con:
        rows = con.execute(
            "SELECT dataset_id FROM rock_mineral_links WHERE rock_id=? ORDER BY dataset_id",
            (int(rock_id),),
        ).fetchall()
    return [int(row[0]) for row in rows]
