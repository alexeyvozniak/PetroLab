from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from petrolab.db import connect
from petrolab.sample_registry import ensure_sample_registry_schema, normalize_sample_key


SOURCE_LABEL_COLUMN = "Статья / источник"
SOURCE_TYPE_COLUMN = "Тип источника"
SOURCE_TITLE_COLUMN = "Название источника"
SOURCE_CITATION_COLUMN = "Цитирование"
SOURCE_DOI_COLUMN = "DOI"
SOURCE_TABLE_COLUMN = "Таблица источника"
UNLINKED_SOURCE_LABEL = "Без статьи / источника"

_SOURCE_TYPE_LABELS = {
    "article": "Статья",
    "colleague": "Данные коллеги",
    "other": "Другой источник",
}


@dataclass(frozen=True)
class HealthIssue:
    kind: str
    severity: str
    title: str
    detail: str
    count: int = 1


def ensure_source_registry_schema() -> None:
    ensure_sample_registry_schema()
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS studies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                source_type TEXT NOT NULL DEFAULT 'article',
                title TEXT NOT NULL DEFAULT '',
                citation TEXT NOT NULL DEFAULT '',
                doi TEXT NOT NULL DEFAULT '',
                authors TEXT NOT NULL DEFAULT '',
                year TEXT NOT NULL DEFAULT '',
                journal TEXT NOT NULL DEFAULT '',
                colleague TEXT NOT NULL DEFAULT '',
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_studies_project ON studies(project_id)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_studies_doi ON studies(doi)")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_studies (
                dataset_id INTEGER PRIMARY KEY,
                study_id INTEGER NOT NULL,
                source_table TEXT NOT NULL DEFAULT '',
                source_note TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                FOREIGN KEY(study_id) REFERENCES studies(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS semantic_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                study_id INTEGER NOT NULL,
                domain TEXT NOT NULL,
                source_label TEXT NOT NULL,
                normalized_value TEXT NOT NULL DEFAULT '',
                author_interpretation TEXT NOT NULL DEFAULT '',
                user_interpretation TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'unresolved',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(study_id, domain, source_label),
                FOREIGN KEY(study_id) REFERENCES studies(id) ON DELETE CASCADE
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_semantic_study ON semantic_mappings(study_id)")
        con.commit()


def create_study(
    project_id: int,
    *,
    source_type: str,
    title: str = "",
    citation: str = "",
    doi: str = "",
    authors: str = "",
    year: str = "",
    journal: str = "",
    colleague: str = "",
    notes: str = "",
) -> int:
    ensure_source_registry_schema()
    clean_type = str(source_type or "other").strip().lower()
    if clean_type not in {"article", "colleague", "other"}:
        clean_type = "other"
    with connect() as con:
        cur = con.execute(
            """
            INSERT INTO studies(project_id, source_type, title, citation, doi, authors, year, journal, colleague, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                int(project_id), clean_type, str(title).strip(), str(citation).strip(), str(doi).strip(),
                str(authors).strip(), str(year).strip(), str(journal).strip(), str(colleague).strip(), str(notes).strip(),
            ),
        )
        con.commit()
        return int(cur.lastrowid)


def list_studies(project_id: int | None = None) -> list[dict]:
    ensure_source_registry_schema()
    with connect() as con:
        if project_id is None:
            rows = con.execute(
                """
                SELECT s.*, p.name AS project_name,
                       COUNT(ds.dataset_id) AS dataset_count
                FROM studies s
                JOIN projects p ON p.id=s.project_id
                LEFT JOIN dataset_studies ds ON ds.study_id=s.id
                GROUP BY s.id
                ORDER BY s.updated_at DESC, s.id DESC
                """
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT s.*, p.name AS project_name,
                       COUNT(ds.dataset_id) AS dataset_count
                FROM studies s
                JOIN projects p ON p.id=s.project_id
                LEFT JOIN dataset_studies ds ON ds.study_id=s.id
                WHERE s.project_id=?
                GROUP BY s.id
                ORDER BY s.updated_at DESC, s.id DESC
                """,
                (int(project_id),),
            ).fetchall()
    return [dict(row) for row in rows]


def _study_display_label(study: dict) -> str:
    """Return a compact, stable label suitable for filters and figure legends."""
    citation = str(study.get("citation") or "").strip()
    title = str(study.get("title") or "").strip()
    colleague = str(study.get("colleague") or "").strip()
    doi = str(study.get("doi") or "").strip()
    year = str(study.get("year") or "").strip()
    label = citation or title or colleague or doi or f"Источник #{int(study['study_id'])}"
    if year and year not in label:
        label = f"{label} ({year})"
    return label


def dataset_study_metadata(dataset_ids: Iterable[int]) -> dict[int, dict]:
    """Return source metadata keyed by dataset, including datasets from linked projects."""
    ids = sorted({int(value) for value in dataset_ids})
    if not ids:
        return {}
    ensure_source_registry_schema()
    rows: list[dict] = []
    with connect() as con:
        for start in range(0, len(ids), 900):
            chunk = ids[start:start + 900]
            placeholders = ",".join("?" for _ in chunk)
            result = con.execute(
                f"""
                SELECT ds.dataset_id, ds.study_id, ds.source_table, ds.source_note,
                       s.source_type, s.title, s.citation, s.doi, s.authors,
                       s.year, s.journal, s.colleague, s.project_id
                FROM dataset_studies ds
                JOIN studies s ON s.id=ds.study_id
                WHERE ds.dataset_id IN ({placeholders})
                ORDER BY ds.dataset_id
                """,
                tuple(chunk),
            ).fetchall()
            rows.extend(dict(row) for row in result)

    base_by_study: dict[int, str] = {}
    for row in rows:
        base_by_study[int(row["study_id"])] = _study_display_label(row)
    label_counts: dict[str, int] = {}
    for label in base_by_study.values():
        label_counts[label] = label_counts.get(label, 0) + 1

    metadata: dict[int, dict] = {}
    for row in rows:
        study_id = int(row["study_id"])
        label = base_by_study[study_id]
        if label_counts[label] > 1:
            label = f"{label} · source #{study_id}"
        metadata[int(row["dataset_id"])] = {
            "study_id": study_id,
            SOURCE_LABEL_COLUMN: label,
            SOURCE_TYPE_COLUMN: _SOURCE_TYPE_LABELS.get(
                str(row.get("source_type") or "").strip().lower(),
                str(row.get("source_type") or "Другой источник"),
            ),
            SOURCE_TITLE_COLUMN: str(row.get("title") or ""),
            SOURCE_CITATION_COLUMN: str(row.get("citation") or ""),
            SOURCE_DOI_COLUMN: str(row.get("doi") or ""),
            SOURCE_TABLE_COLUMN: str(row.get("source_table") or ""),
        }
    return metadata


def attach_study_metadata(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Attach publication/source fields without changing stored analytical rows."""
    result = dataframe.copy()
    if "_dataset_id" not in result.columns:
        result[SOURCE_LABEL_COLUMN] = UNLINKED_SOURCE_LABEL
        result[SOURCE_TYPE_COLUMN] = "Не указан"
        result[SOURCE_TITLE_COLUMN] = ""
        result[SOURCE_CITATION_COLUMN] = ""
        result[SOURCE_DOI_COLUMN] = ""
        result[SOURCE_TABLE_COLUMN] = ""
        result["_study_id"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
        return result

    dataset_ids = pd.to_numeric(result["_dataset_id"], errors="coerce").astype("Int64")
    metadata = dataset_study_metadata(dataset_ids.dropna().astype(int).tolist())
    result[SOURCE_LABEL_COLUMN] = dataset_ids.map(
        lambda value: metadata.get(int(value), {}).get(SOURCE_LABEL_COLUMN, UNLINKED_SOURCE_LABEL)
        if pd.notna(value) else UNLINKED_SOURCE_LABEL
    )
    result[SOURCE_TYPE_COLUMN] = dataset_ids.map(
        lambda value: metadata.get(int(value), {}).get(SOURCE_TYPE_COLUMN, "Не указан")
        if pd.notna(value) else "Не указан"
    )
    for column in (SOURCE_TITLE_COLUMN, SOURCE_CITATION_COLUMN, SOURCE_DOI_COLUMN, SOURCE_TABLE_COLUMN):
        result[column] = dataset_ids.map(
            lambda value, field=column: metadata.get(int(value), {}).get(field, "")
            if pd.notna(value) else ""
        )
    result["_study_id"] = dataset_ids.map(
        lambda value: metadata.get(int(value), {}).get("study_id", pd.NA)
        if pd.notna(value) else pd.NA
    ).astype("Int64")
    return result


def source_labels(dataframe: pd.DataFrame) -> list[str]:
    if SOURCE_LABEL_COLUMN not in dataframe.columns:
        return []
    values = {
        str(value).strip()
        for value in dataframe[SOURCE_LABEL_COLUMN].dropna().tolist()
        if str(value).strip()
    }
    return sorted(values, key=lambda value: (value == UNLINKED_SOURCE_LABEL, value.casefold()))


def filter_visible_sources(
    dataframe: pd.DataFrame,
    visible_sources: Iterable[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split one graph selection into visible and hidden rows without deleting data."""
    if SOURCE_LABEL_COLUMN not in dataframe.columns:
        return dataframe.copy(), dataframe.iloc[0:0].copy()
    wanted = {str(value) for value in visible_sources}
    mask = dataframe[SOURCE_LABEL_COLUMN].astype(str).isin(wanted)
    return dataframe.loc[mask].copy(), dataframe.loc[~mask].copy()


def link_dataset_to_study(dataset_id: int, study_id: int, *, source_table: str = "", source_note: str = "") -> None:
    ensure_source_registry_schema()
    with connect() as con:
        study = con.execute("SELECT project_id FROM studies WHERE id=?", (int(study_id),)).fetchone()
        dataset = con.execute("SELECT id FROM datasets WHERE id=?", (int(dataset_id),)).fetchone()
        if not dataset or not study:
            raise ValueError("Набор данных или источник не найдены")
        membership = con.execute(
            "SELECT 1 FROM project_dataset_links WHERE project_id=? AND dataset_id=?",
            (int(study["project_id"]), int(dataset_id)),
        ).fetchone()
        if not membership:
            raise ValueError("Набор не добавлен в проект источника")
        con.execute(
            """
            INSERT INTO dataset_studies(dataset_id, study_id, source_table, source_note)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(dataset_id) DO UPDATE SET
                study_id=excluded.study_id,
                source_table=excluded.source_table,
                source_note=excluded.source_note
            """,
            (int(dataset_id), int(study_id), str(source_table).strip(), str(source_note).strip()),
        )
        con.commit()


def upsert_semantic_mapping(
    study_id: int,
    *,
    domain: str,
    source_label: str,
    normalized_value: str = "",
    author_interpretation: str = "",
    user_interpretation: str = "",
    status: str = "resolved",
) -> None:
    ensure_source_registry_schema()
    label = str(source_label or "").strip()
    if not label:
        raise ValueError("Исходное обозначение не может быть пустым")
    with connect() as con:
        con.execute(
            """
            INSERT INTO semantic_mappings(
                study_id, domain, source_label, normalized_value,
                author_interpretation, user_interpretation, status, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(study_id, domain, source_label) DO UPDATE SET
                normalized_value=excluded.normalized_value,
                author_interpretation=excluded.author_interpretation,
                user_interpretation=excluded.user_interpretation,
                status=excluded.status,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                int(study_id), str(domain).strip() or "generation", label,
                str(normalized_value).strip(), str(author_interpretation).strip(),
                str(user_interpretation).strip(), str(status).strip() or "resolved",
            ),
        )
        con.commit()


def list_semantic_mappings(study_id: int) -> list[dict]:
    ensure_source_registry_schema()
    with connect() as con:
        rows = con.execute(
            "SELECT * FROM semantic_mappings WHERE study_id=? ORDER BY domain, source_label COLLATE NOCASE",
            (int(study_id),),
        ).fetchall()
    return [dict(row) for row in rows]


def _duplicate_sample_issues(project_id: int | None) -> list[HealthIssue]:
    ensure_source_registry_schema()
    with connect() as con:
        sql = "SELECT project_id, id, name, normalized_key FROM samples"
        params: tuple = ()
        if project_id is not None:
            sql += " WHERE project_id=?"
            params = (int(project_id),)
        rows = con.execute(sql, params).fetchall()
    groups: dict[tuple[int, str], list[str]] = {}
    for row in rows:
        key = str(row["normalized_key"] or normalize_sample_key(str(row["name"])))
        if not key:
            continue
        groups.setdefault((int(row["project_id"]), key), []).append(str(row["name"]))
    issues: list[HealthIssue] = []
    for (_, _), names in groups.items():
        unique = sorted(set(names), key=str.casefold)
        if len(unique) > 1:
            issues.append(HealthIssue(
                kind="sample_duplicate", severity="warning",
                title="Возможный дубль образца",
                detail=" · ".join(unique), count=len(unique),
            ))
    return issues


def database_health(project_id: int | None = None) -> dict:
    ensure_source_registry_schema()
    issues = _duplicate_sample_issues(project_id)
    with connect() as con:
        where_d = "" if project_id is None else " WHERE d.project_id=?"
        params: tuple = () if project_id is None else (int(project_id),)
        unlinked_datasets = int(con.execute(
            f"SELECT COUNT(*) FROM datasets d LEFT JOIN dataset_studies ds ON ds.dataset_id=d.id{where_d}"
            + (" AND ds.dataset_id IS NULL" if project_id is not None else " WHERE ds.dataset_id IS NULL"),
            params,
        ).fetchone()[0])
        unresolved = int(con.execute(
            """
            SELECT COUNT(*) FROM semantic_mappings m
            JOIN studies s ON s.id=m.study_id
            WHERE m.status='unresolved'
            """ + (" AND s.project_id=?" if project_id is not None else ""),
            params,
        ).fetchone()[0])
        if project_id is None:
            analysis_without_sample = int(con.execute(
                "SELECT COUNT(*) FROM analysis_rows a JOIN datasets d ON d.id=a.dataset_id WHERE d.sample_id IS NULL"
            ).fetchone()[0])
        else:
            analysis_without_sample = int(con.execute(
                "SELECT COUNT(*) FROM analysis_rows a JOIN datasets d ON d.id=a.dataset_id WHERE d.project_id=? AND d.sample_id IS NULL",
                (int(project_id),),
            ).fetchone()[0])
        studies_incomplete = int(con.execute(
            "SELECT COUNT(*) FROM studies WHERE (title='' AND citation='' AND doi='' AND colleague='')"
            + (" AND project_id=?" if project_id is not None else ""),
            params,
        ).fetchone()[0])

    if unlinked_datasets:
        issues.append(HealthIssue("unlinked_source", "info", "Наборы без Study/Source", "Источник можно добавить позже; данные уже доступны.", unlinked_datasets))
    if unresolved:
        issues.append(HealthIssue("semantic_unresolved", "info", "Несопоставленные авторские категории", "Они не блокируют графики и статистику.", unresolved))
    if analysis_without_sample:
        issues.append(HealthIssue("analysis_without_sample", "warning", "Анализы без canonical Sample", "Их можно привязать к образцам позже.", analysis_without_sample))
    if studies_incomplete:
        issues.append(HealthIssue("study_metadata", "info", "Источники с минимальными metadata", "Библиографию можно дополнить позже.", studies_incomplete))

    penalty = sum(min(issue.count, 20) for issue in issues)
    score = max(0, 100 - min(70, penalty))
    return {
        "score": score,
        "issues": issues,
        "issue_count": len(issues),
        "unlinked_datasets": unlinked_datasets,
        "unresolved_mappings": unresolved,
        "analysis_without_sample": analysis_without_sample,
        "incomplete_studies": studies_incomplete,
    }
