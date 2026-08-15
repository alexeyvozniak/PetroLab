from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from petrolab.repositories.rock_repository import rock_connection


@dataclass(frozen=True)
class RockDetermination:
    id: int
    rock_id: int
    study_id: int | None
    label: str
    source_label: str
    method: str
    laboratory: str
    source_file: str
    source_sheet: str
    is_preferred: bool


def ensure_rock_determination_schema() -> None:
    with rock_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS rock_determinations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                rock_id INTEGER NOT NULL,
                study_id INTEGER,
                label TEXT NOT NULL DEFAULT '',
                source_label TEXT NOT NULL DEFAULT '',
                method TEXT NOT NULL DEFAULT '',
                laboratory TEXT NOT NULL DEFAULT '',
                source_file TEXT NOT NULL DEFAULT '',
                source_sheet TEXT NOT NULL DEFAULT '',
                source_row INTEGER,
                is_preferred INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(rock_id) REFERENCES rock_samples(id) ON DELETE CASCADE,
                FOREIGN KEY(study_id) REFERENCES studies(id) ON DELETE SET NULL
            )
            """
        )
        columns = {str(row[1]) for row in con.execute("PRAGMA table_info(rock_determinations)").fetchall()}
        if "study_id" not in columns:
            con.execute("ALTER TABLE rock_determinations ADD COLUMN study_id INTEGER")
        con.execute("CREATE INDEX IF NOT EXISTS idx_rock_det_rock ON rock_determinations(rock_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_rock_det_source ON rock_determinations(source_label)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_rock_det_study ON rock_determinations(study_id)")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS rock_determination_values (
                determination_id INTEGER NOT NULL,
                analyte TEXT NOT NULL,
                value REAL NOT NULL,
                unit TEXT NOT NULL DEFAULT '',
                PRIMARY KEY(determination_id, analyte),
                FOREIGN KEY(determination_id) REFERENCES rock_determinations(id) ON DELETE CASCADE
            )
            """
        )
        con.commit()


def create_rock_determination(
    rock_id: int,
    composition: dict[str, float],
    *,
    units: dict[str, str] | None = None,
    study_id: int | None = None,
    label: str = "",
    source_label: str = "",
    method: str = "",
    laboratory: str = "",
    source_file: str = "",
    source_sheet: str = "",
    source_row: int | None = None,
    preferred: bool | None = None,
) -> int:
    ensure_rock_determination_schema()
    units = units or {}
    with rock_connection() as con:
        existing_count = int(con.execute(
            "SELECT COUNT(*) FROM rock_determinations WHERE rock_id=?", (int(rock_id),)
        ).fetchone()[0])
        is_preferred = existing_count == 0 if preferred is None else bool(preferred)
        if is_preferred:
            con.execute("UPDATE rock_determinations SET is_preferred=0 WHERE rock_id=?", (int(rock_id),))
        cur = con.execute(
            """
            INSERT INTO rock_determinations(
                rock_id, study_id, label, source_label, method, laboratory, source_file,
                source_sheet, source_row, is_preferred, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                int(rock_id), int(study_id) if study_id is not None else None,
                str(label).strip(), str(source_label).strip(), str(method).strip(),
                str(laboratory).strip(), str(source_file).strip(), str(source_sheet).strip(),
                int(source_row) if source_row is not None else None, 1 if is_preferred else 0,
            ),
        )
        determination_id = int(cur.lastrowid)
        for analyte, value in composition.items():
            try:
                numeric = float(value)
            except (TypeError, ValueError):
                continue
            con.execute(
                "INSERT INTO rock_determination_values(determination_id, analyte, value, unit) VALUES (?, ?, ?, ?)",
                (determination_id, str(analyte), numeric, str(units.get(str(analyte), ""))),
            )
        con.commit()
        return determination_id


def list_rock_determinations(rock_id: int) -> list[dict]:
    ensure_rock_determination_schema()
    with rock_connection() as con:
        rows = con.execute(
            """
            SELECT d.*, COALESCE(NULLIF(s.citation,''), NULLIF(s.title,''), d.source_label) AS study_label
            FROM rock_determinations d LEFT JOIN studies s ON s.id=d.study_id
            WHERE d.rock_id=? ORDER BY d.is_preferred DESC, d.id DESC
            """,
            (int(rock_id),),
        ).fetchall()
        result: list[dict] = []
        for row in rows:
            item = dict(row)
            values = con.execute(
                "SELECT analyte, value, unit FROM rock_determination_values WHERE determination_id=? ORDER BY analyte",
                (int(row["id"]),),
            ).fetchall()
            item["composition"] = {str(value["analyte"]): float(value["value"]) for value in values}
            item["units"] = {str(value["analyte"]): str(value["unit"] or "") for value in values}
            result.append(item)
    return result


def determination_dataframe(project_id: int | None = None) -> pd.DataFrame:
    ensure_rock_determination_schema()
    with rock_connection() as con:
        sql = """
            SELECT d.*, r.project_id, r.name AS Sample, r.lithology AS Lithology,
                   r.massif AS Massif, r.locality AS Locality,
                   COALESCE(NULLIF(s.citation,''), NULLIF(s.title,''), d.source_label) AS Source
            FROM rock_determinations d
            JOIN rock_samples r ON r.id=d.rock_id
            LEFT JOIN studies s ON s.id=d.study_id
        """
        params: tuple = ()
        if project_id is not None:
            sql += " WHERE r.project_id=?"
            params = (int(project_id),)
        sql += " ORDER BY r.name, d.is_preferred DESC, d.id"
        rows = [dict(row) for row in con.execute(sql, params).fetchall()]
        records: list[dict] = []
        for row in rows:
            values = con.execute(
                "SELECT analyte, value FROM rock_determination_values WHERE determination_id=?",
                (int(row["id"]),),
            ).fetchall()
            records.append({
                **row,
                **{str(value["analyte"]): float(value["value"]) for value in values},
                "Method": str(row.get("method") or ""),
            })
    return pd.DataFrame(records)


def set_preferred_determination(rock_id: int, determination_id: int) -> None:
    ensure_rock_determination_schema()
    with rock_connection() as con:
        found = con.execute(
            "SELECT 1 FROM rock_determinations WHERE id=? AND rock_id=?",
            (int(determination_id), int(rock_id)),
        ).fetchone()
        if not found:
            raise ValueError("Определение не принадлежит выбранному образцу")
        con.execute("UPDATE rock_determinations SET is_preferred=0 WHERE rock_id=?", (int(rock_id),))
        con.execute("UPDATE rock_determinations SET is_preferred=1, updated_at=CURRENT_TIMESTAMP WHERE id=?", (int(determination_id),))
        con.commit()
