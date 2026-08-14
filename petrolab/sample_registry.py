from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from petrolab.db import connect


_SEPARATOR_RE = re.compile(r"[\s_\-–—./\\]+", re.UNICODE)


def normalize_sample_key(value: str) -> str:
    """Return a conservative comparison key for sample-name suggestions.

    The key is only used to find likely duplicates. PetroLab must never merge samples
    automatically solely because these keys match.
    """
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    text = _SEPARATOR_RE.sub("", text)
    return "".join(ch for ch in text if ch.isalnum())


@dataclass(frozen=True)
class SampleMatch:
    sample_id: int
    canonical_name: str
    matched_name: str
    match_kind: str


def ensure_sample_registry_schema() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS samples (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                normalized_key TEXT NOT NULL DEFAULT '',
                field_lithology TEXT NOT NULL DEFAULT '',
                locality TEXT NOT NULL DEFAULT '',
                latitude REAL,
                longitude REAL,
                description TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, name),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        cols = {str(row[1]) for row in con.execute("PRAGMA table_info(samples)").fetchall()}
        additions = {
            "normalized_key": "TEXT NOT NULL DEFAULT ''",
            "field_lithology": "TEXT NOT NULL DEFAULT ''",
            "locality": "TEXT NOT NULL DEFAULT ''",
            "latitude": "REAL",
            "longitude": "REAL",
            "notes": "TEXT NOT NULL DEFAULT ''",
            "updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for name, ddl in additions.items():
            if name not in cols:
                con.execute(f"ALTER TABLE samples ADD COLUMN {name} {ddl}")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS sample_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sample_id INTEGER NOT NULL,
                alias TEXT NOT NULL,
                normalized_key TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'manual',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(sample_id, alias),
                FOREIGN KEY(sample_id) REFERENCES samples(id) ON DELETE CASCADE
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_samples_project_key ON samples(project_id, normalized_key)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sample_alias_key ON sample_aliases(normalized_key)")
        rows = con.execute("SELECT id, name, normalized_key FROM samples").fetchall()
        for row in rows:
            key = normalize_sample_key(str(row["name"]))
            if key and str(row["normalized_key"] or "") != key:
                con.execute("UPDATE samples SET normalized_key=? WHERE id=?", (key, int(row["id"])))
        # Link existing whole-rock records to the universal sample registry without deleting legacy data.
        rock_tables = {str(row[0]) for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "rock_samples" in rock_tables:
            rock_cols = {str(row[1]) for row in con.execute("PRAGMA table_info(rock_samples)").fetchall()}
            if "sample_id" not in rock_cols:
                con.execute("ALTER TABLE rock_samples ADD COLUMN sample_id INTEGER")
            con.execute("CREATE INDEX IF NOT EXISTS idx_rock_sample_registry ON rock_samples(sample_id)")
        dataset_cols = {str(row[1]) for row in con.execute("PRAGMA table_info(datasets)").fetchall()}
        if "sample_id" not in dataset_cols:
            con.execute("ALTER TABLE datasets ADD COLUMN sample_id INTEGER")
        if "session_id" not in dataset_cols:
            con.execute("ALTER TABLE datasets ADD COLUMN session_id INTEGER")
        con.execute("CREATE INDEX IF NOT EXISTS idx_datasets_sample_registry ON datasets(sample_id)")
        con.commit()


def find_sample_matches(project_id: int, proposed_name: str) -> list[SampleMatch]:
    ensure_sample_registry_schema()
    proposed = str(proposed_name or "").strip()
    if not proposed:
        return []
    key = normalize_sample_key(proposed)
    with connect() as con:
        rows = con.execute(
            "SELECT id, name, normalized_key FROM samples WHERE project_id=? ORDER BY name COLLATE NOCASE",
            (int(project_id),),
        ).fetchall()
        aliases = con.execute(
            """
            SELECT a.sample_id, a.alias, a.normalized_key, s.name
            FROM sample_aliases a JOIN samples s ON s.id=a.sample_id
            WHERE s.project_id=?
            """,
            (int(project_id),),
        ).fetchall()
    result: dict[int, SampleMatch] = {}
    for row in rows:
        if str(row["name"]).casefold() == proposed.casefold():
            result[int(row["id"])] = SampleMatch(int(row["id"]), str(row["name"]), str(row["name"]), "exact")
        elif key and str(row["normalized_key"] or "") == key:
            result.setdefault(int(row["id"]), SampleMatch(int(row["id"]), str(row["name"]), str(row["name"]), "normalized"))
    for row in aliases:
        if str(row["alias"]).casefold() == proposed.casefold() or (key and str(row["normalized_key"] or "") == key):
            result.setdefault(int(row["sample_id"]), SampleMatch(int(row["sample_id"]), str(row["name"]), str(row["alias"]), "alias"))
    order = {"exact": 0, "alias": 1, "normalized": 2}
    return sorted(result.values(), key=lambda item: (order.get(item.match_kind, 9), item.canonical_name.casefold()))


def create_sample(
    project_id: int,
    name: str,
    *,
    field_lithology: str = "",
    locality: str = "",
    latitude: float | None = None,
    longitude: float | None = None,
    description: str = "",
    notes: str = "",
) -> int:
    ensure_sample_registry_schema()
    clean = str(name or "").strip()
    if not clean:
        raise ValueError("Укажите название образца")
    with connect() as con:
        cur = con.execute(
            """
            INSERT INTO samples(project_id, name, normalized_key, field_lithology, locality,
                                latitude, longitude, description, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (int(project_id), clean, normalize_sample_key(clean), str(field_lithology).strip(),
             str(locality).strip(), latitude, longitude, str(description).strip(), str(notes).strip()),
        )
        con.commit()
        return int(cur.lastrowid)


def add_sample_alias(sample_id: int, alias: str, *, source: str = "manual") -> None:
    ensure_sample_registry_schema()
    clean = str(alias or "").strip()
    if not clean:
        return
    with connect() as con:
        con.execute(
            """
            INSERT INTO sample_aliases(sample_id, alias, normalized_key, source)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(sample_id, alias) DO UPDATE SET normalized_key=excluded.normalized_key, source=excluded.source
            """,
            (int(sample_id), clean, normalize_sample_key(clean), str(source).strip() or "manual"),
        )
        con.commit()


def list_samples(project_id: int | None = None) -> list[dict]:
    ensure_sample_registry_schema()
    with connect() as con:
        if project_id is None:
            rows = con.execute(
                "SELECT s.*, p.name AS project_name FROM samples s JOIN projects p ON p.id=s.project_id ORDER BY p.name, s.name COLLATE NOCASE"
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT s.*, p.name AS project_name FROM samples s JOIN projects p ON p.id=s.project_id WHERE s.project_id=? ORDER BY s.name COLLATE NOCASE",
                (int(project_id),),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            aliases = con.execute("SELECT alias FROM sample_aliases WHERE sample_id=? ORDER BY alias COLLATE NOCASE", (int(row["id"]),)).fetchall()
            item["aliases"] = [str(alias[0]) for alias in aliases]
            result.append(item)
    return result


def link_rock_record_to_sample(rock_id: int, sample_id: int) -> None:
    ensure_sample_registry_schema()
    with connect() as con:
        sample = con.execute("SELECT project_id FROM samples WHERE id=?", (int(sample_id),)).fetchone()
        rock = con.execute("SELECT project_id FROM rock_samples WHERE id=?", (int(rock_id),)).fetchone()
        if not sample or not rock:
            raise ValueError("Образец или запись породы не найдены")
        if int(sample["project_id"]) != int(rock["project_id"]):
            raise ValueError("Нельзя связать записи из разных проектов")
        con.execute("UPDATE rock_samples SET sample_id=? WHERE id=?", (int(sample_id), int(rock_id)))
        con.commit()
