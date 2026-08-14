from __future__ import annotations

import json
from datetime import date
from typing import Iterable

from petrolab.db import connect
from petrolab.sample_registry import ensure_sample_registry_schema


TECHNIQUES = {
    "EPMA_WDS": "Электронный микрозонд · WDS",
    "SEM_EDS": "SEM · EDS",
    "EPMA_EDS": "Электронный микрозонд · EDS",
    "LA_ICP_MS": "LA-ICP-MS",
    "XRF": "XRF",
    "ICP_MS": "ICP-MS / solution",
    "OTHER": "Другое",
}

SESSION_STATUSES = {"draft": "Разбор", "review": "Проверка", "complete": "Готово"}
MORPHOLOGY_KEYS = {
    "zone": "Положение в зерне",
    "grain_size": "Размер зерна",
    "textural_role": "Текстурная позиция",
    "note": "Морфологическая заметка",
}


def ensure_session_schema() -> None:
    ensure_sample_registry_schema()
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS analytical_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                sample_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                session_date TEXT NOT NULL DEFAULT '',
                technique TEXT NOT NULL DEFAULT 'OTHER',
                facility TEXT NOT NULL DEFAULT '',
                instrument TEXT NOT NULL DEFAULT '',
                operator TEXT NOT NULL DEFAULT '',
                mode TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft',
                tags_json TEXT NOT NULL DEFAULT '[]',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY(sample_id) REFERENCES samples(id) ON DELETE CASCADE
            )
            """
        )
        columns = {str(row[1]) for row in con.execute("PRAGMA table_info(datasets)").fetchall()}
        if "session_id" not in columns:
            con.execute("ALTER TABLE datasets ADD COLUMN session_id INTEGER")
        if "sample_id" not in columns:
            con.execute("ALTER TABLE datasets ADD COLUMN sample_id INTEGER")
        con.execute("CREATE INDEX IF NOT EXISTS idx_datasets_session ON datasets(session_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_datasets_sample ON datasets(sample_id)")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_annotations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                analysis_id TEXT NOT NULL,
                namespace TEXT NOT NULL DEFAULT 'morphology',
                key TEXT NOT NULL,
                value TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'manual',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(analysis_id, namespace, key),
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_annotations_analysis ON analysis_annotations(analysis_id)")
        con.commit()


def create_session(project_id: int, sample_id: int, *, name: str = "", session_date: str | date = "", technique: str = "OTHER", facility: str = "", instrument: str = "", operator: str = "", mode: str = "", notes: str = "", tags: Iterable[str] = ()) -> int:
    ensure_session_schema()
    technique = technique if technique in TECHNIQUES else "OTHER"
    date_text = session_date.isoformat() if isinstance(session_date, date) else str(session_date).strip()
    clean_name = str(name).strip() or f"{TECHNIQUES[technique]} · {date_text or 'без даты'}"
    clean_tags = [str(tag).strip() for tag in tags if str(tag).strip()]
    with connect() as con:
        sample = con.execute("SELECT id FROM samples WHERE id=? AND project_id=?", (int(sample_id), int(project_id))).fetchone()
        if not sample:
            raise ValueError("Образец не относится к активному проекту")
        cur = con.execute(
            """INSERT INTO analytical_sessions(project_id, sample_id, name, session_date, technique, facility, instrument, operator, mode, notes, tags_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (int(project_id), int(sample_id), clean_name, date_text, technique, str(facility).strip(), str(instrument).strip(), str(operator).strip(), str(mode).strip(), str(notes).strip(), json.dumps(clean_tags, ensure_ascii=False)),
        )
        con.commit()
        return int(cur.lastrowid)


def list_sessions(project_id: int, sample_id: int | None = None) -> list[dict]:
    ensure_session_schema()
    query = "SELECT s.*, sm.name AS sample_name FROM analytical_sessions s JOIN samples sm ON sm.id=s.sample_id WHERE s.project_id=?"
    params: list[object] = [int(project_id)]
    if sample_id is not None:
        query += " AND s.sample_id=?"
        params.append(int(sample_id))
    query += " ORDER BY COALESCE(NULLIF(s.session_date,''), s.created_at) DESC, s.id DESC"
    with connect() as con:
        rows = con.execute(query, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        try:
            item["tags"] = json.loads(item.pop("tags_json", "[]"))
        except json.JSONDecodeError:
            item["tags"] = []
        result.append(item)
    return result


def update_session_status(session_id: int, status: str) -> None:
    ensure_session_schema()
    if status not in SESSION_STATUSES:
        raise ValueError("Неизвестный статус сессии")
    with connect() as con:
        con.execute("UPDATE analytical_sessions SET status=?, updated_at=CURRENT_TIMESTAMP WHERE id=?", (status, int(session_id)))
        con.commit()


def attach_datasets(session_id: int, dataset_ids: Iterable[int]) -> int:
    ensure_session_schema()
    ids = list(dict.fromkeys(int(value) for value in dataset_ids))
    if not ids:
        return 0
    with connect() as con:
        session = con.execute("SELECT project_id, sample_id FROM analytical_sessions WHERE id=?", (int(session_id),)).fetchone()
        if not session:
            raise ValueError("Сессия не найдена")
        placeholders = ",".join("?" for _ in ids)
        datasets = con.execute(f"SELECT id, project_id, sample_id FROM datasets WHERE id IN ({placeholders})", ids).fetchall()
        found = {int(row["id"]): row for row in datasets}
        missing = [value for value in ids if value not in found]
        if missing:
            raise ValueError(f"Не найдены наборы: {missing}")
        if any(int(row["project_id"]) != int(session["project_id"]) for row in found.values()):
            raise ValueError("Нельзя привязать набор из другого проекта")
        if any(row["sample_id"] is not None and int(row["sample_id"]) != int(session["sample_id"]) for row in found.values()):
            raise ValueError("Нельзя перепривязать набор, уже относящийся к другому canonical Sample")
        con.executemany("UPDATE datasets SET session_id=?, sample_id=? WHERE id=?", [(int(session_id), int(session["sample_id"]), dataset_id) for dataset_id in ids])
        con.commit()
    return len(ids)


def session_datasets(session_id: int) -> list[dict]:
    ensure_session_schema()
    with connect() as con:
        rows = con.execute("SELECT d.* FROM datasets d WHERE d.session_id=? ORDER BY d.mineral_key, d.name", (int(session_id),)).fetchall()
    return [dict(row) for row in rows]


def sample_history(project_id: int, sample_id: int) -> dict:
    ensure_session_schema()
    with connect() as con:
        sample = con.execute("SELECT * FROM samples WHERE id=? AND project_id=?", (int(sample_id), int(project_id))).fetchone()
        if not sample:
            raise ValueError("Образец не найден")
        sessions = con.execute(
            """SELECT s.*, COUNT(DISTINCT d.id) AS dataset_count, COALESCE(SUM(d.row_count),0) AS analysis_count
               FROM analytical_sessions s LEFT JOIN datasets d ON d.session_id=s.id
               WHERE s.sample_id=? GROUP BY s.id
               ORDER BY COALESCE(NULLIF(s.session_date,''), s.created_at) DESC""",
            (int(sample_id),),
        ).fetchall()
    return {"sample": dict(sample), "sessions": [dict(row) for row in sessions]}


def set_annotations(analysis_ids: Iterable[str], values: dict[str, str], *, namespace: str = "morphology", source: str = "manual") -> int:
    ensure_session_schema()
    ids = [str(value).strip() for value in analysis_ids if str(value).strip()]
    clean = {str(key).strip(): str(value).strip() for key, value in values.items() if str(key).strip() and str(value).strip()}
    if not ids or not clean:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with connect() as con:
        existing = {str(row["analysis_id"]) for row in con.execute(f"SELECT analysis_id FROM analysis_rows WHERE analysis_id IN ({placeholders})", ids).fetchall()}
        missing = [value for value in ids if value not in existing]
        if missing:
            raise ValueError(f"Не найдены анализы: {missing[:5]}")
        rows = [(analysis_id, namespace, key, value, source) for analysis_id in ids for key, value in clean.items()]
        con.executemany(
            """INSERT INTO analysis_annotations(analysis_id, namespace, key, value, source, updated_at)
               VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
               ON CONFLICT(analysis_id, namespace, key) DO UPDATE SET value=excluded.value, source=excluded.source, updated_at=CURRENT_TIMESTAMP""",
            rows,
        )
        con.commit()
    return len(ids)


def annotation_table(analysis_ids: Iterable[str], *, namespace: str = "morphology") -> dict[str, dict[str, str]]:
    ensure_session_schema()
    ids = [str(value).strip() for value in analysis_ids if str(value).strip()]
    if not ids:
        return {}
    placeholders = ",".join("?" for _ in ids)
    with connect() as con:
        rows = con.execute(f"SELECT analysis_id, key, value FROM analysis_annotations WHERE namespace=? AND analysis_id IN ({placeholders})", [namespace, *ids]).fetchall()
    result: dict[str, dict[str, str]] = {}
    for row in rows:
        result.setdefault(str(row["analysis_id"]), {})[str(row["key"])] = str(row["value"])
    return result
