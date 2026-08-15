from __future__ import annotations

from typing import Iterable
import unicodedata

from petrolab.db import connect


DEFAULT_TERM_DOMAINS = (
    "Lithology", "Mineral", "Generation", "Method", "Laboratory", "Locality", "Massif",
)


def _literal_key(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    return " ".join(text.split())


def ensure_term_registry_schema() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS canonical_terms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                domain TEXT NOT NULL,
                canonical_value TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(project_id, domain, canonical_value),
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_terms_project_domain ON canonical_terms(project_id, domain)")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS canonical_term_aliases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                term_id INTEGER NOT NULL,
                alias TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'staging_confirmed',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(term_id, alias),
                FOREIGN KEY(term_id) REFERENCES canonical_terms(id) ON DELETE CASCADE
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_term_aliases_term ON canonical_term_aliases(term_id)")
        con.commit()


def list_terms(project_id: int, domain: str) -> list[dict]:
    ensure_term_registry_schema()
    with connect() as con:
        rows = con.execute(
            """
            SELECT * FROM canonical_terms
            WHERE project_id=? AND domain=?
            ORDER BY canonical_value COLLATE NOCASE
            """,
            (int(project_id), str(domain)),
        ).fetchall()
        result: list[dict] = []
        for row in rows:
            aliases = con.execute(
                "SELECT alias FROM canonical_term_aliases WHERE term_id=? ORDER BY alias COLLATE NOCASE",
                (int(row["id"]),),
            ).fetchall()
            item = dict(row)
            item["aliases"] = [str(alias[0]) for alias in aliases]
            result.append(item)
    return result


def term_values(project_id: int, domain: str) -> list[str]:
    return [str(item["canonical_value"]) for item in list_terms(int(project_id), str(domain))]


def find_exact_term(project_id: int, domain: str, value: str) -> dict | None:
    key = _literal_key(value)
    if not key:
        return None
    for item in list_terms(int(project_id), str(domain)):
        if _literal_key(item["canonical_value"]) == key:
            return item
        if any(_literal_key(alias) == key for alias in item.get("aliases", [])):
            return item
    return None


def register_term(
    project_id: int,
    domain: str,
    canonical_value: str,
    *,
    aliases: Iterable[str] = (),
    source: str = "staging_confirmed",
) -> int:
    ensure_term_registry_schema()
    canonical = str(canonical_value or "").strip()
    if not canonical:
        raise ValueError("Каноническое значение не может быть пустым")
    exact = find_exact_term(int(project_id), str(domain), canonical)
    with connect() as con:
        if exact is None:
            cur = con.execute(
                """
                INSERT INTO canonical_terms(project_id, domain, canonical_value, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (int(project_id), str(domain), canonical),
            )
            term_id = int(cur.lastrowid)
        else:
            term_id = int(exact["id"])
        for raw in aliases:
            alias = str(raw or "").strip()
            if not alias or _literal_key(alias) == _literal_key(canonical):
                continue
            con.execute(
                """
                INSERT INTO canonical_term_aliases(term_id, alias, source)
                VALUES (?, ?, ?)
                ON CONFLICT(term_id, alias) DO UPDATE SET source=excluded.source
                """,
                (term_id, alias, str(source or "staging_confirmed")),
            )
        con.commit()
    return term_id


def persist_staged_terms(
    project_id: int,
    dataframe,
    confirmations: dict[str, dict[str, str]] | None = None,
) -> int:
    """Remember canonical categorical values and user-confirmed aliases after import."""
    confirmations = confirmations or {}
    stored = 0
    for domain in DEFAULT_TERM_DOMAINS:
        if domain not in dataframe.columns:
            continue
        values = {
            str(value).strip()
            for value in dataframe[domain].dropna().tolist()
            if str(value).strip()
        }
        aliases_by_canonical: dict[str, list[str]] = {}
        for alias, canonical in confirmations.get(domain, {}).items():
            aliases_by_canonical.setdefault(str(canonical), []).append(str(alias))
        for canonical in sorted(values, key=str.casefold):
            register_term(
                int(project_id),
                domain,
                canonical,
                aliases=aliases_by_canonical.get(canonical, ()),
            )
            stored += 1
    return stored
