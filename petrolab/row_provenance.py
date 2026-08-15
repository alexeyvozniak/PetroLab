from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable
import unicodedata

import pandas as pd

from petrolab.db import connect, load_dataset_dataframe
from petrolab.import_staging import similar_name_candidates
from petrolab.sample_registry import add_sample_alias, create_sample, list_samples
from petrolab.source_registry import create_study, list_studies


@dataclass(frozen=True)
class ReconciliationCandidate:
    domain: str
    incoming: str
    existing_id: int
    existing: str
    score: float
    reason: str


def ensure_row_provenance_schema() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_sample_links (
                analysis_id TEXT PRIMARY KEY,
                sample_id INTEGER NOT NULL,
                source_label TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(sample_id) REFERENCES samples(id) ON DELETE CASCADE
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_analysis_sample_sample ON analysis_sample_links(sample_id)")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_studies (
                analysis_id TEXT PRIMARY KEY,
                study_id INTEGER NOT NULL,
                source_label TEXT NOT NULL DEFAULT '',
                source_table TEXT NOT NULL DEFAULT '',
                source_note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(study_id) REFERENCES studies(id) ON DELETE CASCADE
            )
            """
        )
        con.execute("CREATE INDEX IF NOT EXISTS idx_analysis_study_study ON analysis_studies(study_id)")
        con.commit()


def _clean_unique(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        if raw is None:
            continue
        try:
            if pd.isna(raw):
                continue
        except (TypeError, ValueError):
            pass
        value = str(raw).strip()
        if not value:
            continue
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _literal_key(value: object) -> str:
    """Exact identity key: typographic/case normalization only, no transliteration or fuzzy matching."""
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold().replace("ё", "е")
    return " ".join(text.split())


def sample_reconciliation_candidates(project_id: int, incoming: Iterable[object]) -> list[ReconciliationCandidate]:
    existing = list_samples(int(project_id))
    by_name = {str(item["name"]): int(item["id"]) for item in existing}
    suggestions = similar_name_candidates(_clean_unique(incoming), by_name)
    return [
        ReconciliationCandidate("sample", item.incoming, by_name[item.existing], item.existing, item.score, item.reason)
        for item in suggestions
    ]


def source_reconciliation_candidates(project_id: int, incoming: Iterable[object]) -> list[ReconciliationCandidate]:
    studies = list_studies(int(project_id))
    labels: dict[str, int] = {}
    for study in studies:
        label = str(study.get("citation") or study.get("title") or study.get("doi") or "").strip()
        if label:
            labels[label] = int(study["id"])
    suggestions = similar_name_candidates(_clean_unique(incoming), labels)
    return [
        ReconciliationCandidate("source", item.incoming, labels[item.existing], item.existing, item.score, item.reason)
        for item in suggestions
    ]


def _find_exact_sample(project_id: int, label: str) -> dict | None:
    key = _literal_key(label)
    for item in list_samples(int(project_id)):
        if _literal_key(item.get("name", "")) == key:
            return item
        for alias in item.get("aliases", []):
            if _literal_key(alias) == key:
                return item
    return None


def _find_exact_study(project_id: int, label: str) -> dict | None:
    key = _literal_key(label)
    for item in list_studies(int(project_id)):
        for field in ("citation", "title", "doi"):
            value = str(item.get(field) or "").strip()
            if value and _literal_key(value) == key:
                return item
    return None


def canonical_sample_id(
    project_id: int,
    label: str,
    *,
    confirmed_existing_id: int | None = None,
    create_if_missing: bool = True,
) -> int | None:
    clean = str(label or "").strip()
    if not clean:
        return None
    if confirmed_existing_id is not None:
        sample_id = int(confirmed_existing_id)
        add_sample_alias(sample_id, clean, source="staging_confirmed")
        return sample_id
    exact = _find_exact_sample(int(project_id), clean)
    if exact is not None:
        return int(exact["id"])
    if not create_if_missing:
        return None
    return int(create_sample(int(project_id), clean))


def canonical_study_id(
    project_id: int,
    label: str,
    *,
    confirmed_existing_id: int | None = None,
    create_if_missing: bool = True,
) -> int | None:
    clean = str(label or "").strip()
    if not clean:
        return None
    if confirmed_existing_id is not None:
        return int(confirmed_existing_id)
    exact = _find_exact_study(int(project_id), clean)
    if exact is not None:
        return int(exact["id"])
    if not create_if_missing:
        return None
    return int(create_study(int(project_id), source_type="article", citation=clean, title=clean))


def link_analysis_to_sample(analysis_id: str, sample_id: int, *, source_label: str = "") -> None:
    ensure_row_provenance_schema()
    with connect() as con:
        con.execute(
            """
            INSERT INTO analysis_sample_links(analysis_id, sample_id, source_label, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(analysis_id) DO UPDATE SET
                sample_id=excluded.sample_id,
                source_label=excluded.source_label,
                updated_at=CURRENT_TIMESTAMP
            """,
            (str(analysis_id), int(sample_id), str(source_label).strip()),
        )
        con.commit()


def link_analysis_to_study(analysis_id: str, study_id: int, *, source_label: str = "", source_table: str = "") -> None:
    ensure_row_provenance_schema()
    with connect() as con:
        con.execute(
            """
            INSERT INTO analysis_studies(analysis_id, study_id, source_label, source_table, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(analysis_id) DO UPDATE SET
                study_id=excluded.study_id,
                source_label=excluded.source_label,
                source_table=excluded.source_table,
                updated_at=CURRENT_TIMESTAMP
            """,
            (str(analysis_id), int(study_id), str(source_label).strip(), str(source_table).strip()),
        )
        con.commit()


def attach_row_provenance(dataframe: pd.DataFrame) -> pd.DataFrame:
    ensure_row_provenance_schema()
    result = dataframe.copy()
    if "_analysis_id" not in result.columns or result.empty:
        return result
    ids = result["_analysis_id"].dropna().astype(str).tolist()
    sample_meta: dict[str, tuple[int, str, str]] = {}
    source_meta: dict[str, tuple[int, str]] = {}
    with connect() as con:
        for start in range(0, len(ids), 900):
            chunk = ids[start:start + 900]
            placeholders = ",".join("?" for _ in chunk)
            rows = con.execute(
                f"""
                SELECT l.analysis_id, l.sample_id, l.source_label, s.name
                FROM analysis_sample_links l JOIN samples s ON s.id=l.sample_id
                WHERE l.analysis_id IN ({placeholders})
                """, tuple(chunk)
            ).fetchall()
            for row in rows:
                sample_meta[str(row["analysis_id"])] = (int(row["sample_id"]), str(row["name"]), str(row["source_label"] or ""))
            rows = con.execute(
                f"""
                SELECT l.analysis_id, l.study_id,
                       COALESCE(NULLIF(s.citation,''), NULLIF(s.title,''), NULLIF(s.doi,''), 'Источник #' || s.id) AS label
                FROM analysis_studies l JOIN studies s ON s.id=l.study_id
                WHERE l.analysis_id IN ({placeholders})
                """, tuple(chunk)
            ).fetchall()
            for row in rows:
                source_meta[str(row["analysis_id"])] = (int(row["study_id"]), str(row["label"]))
    result["Canonical Sample"] = result["_analysis_id"].astype(str).map(lambda value: sample_meta.get(value, (None, "", ""))[1])
    result["_canonical_sample_id"] = result["_analysis_id"].astype(str).map(lambda value: sample_meta.get(value, (None, "", ""))[0]).astype("Int64")
    result["Row Source"] = result["_analysis_id"].astype(str).map(lambda value: source_meta.get(value, (None, ""))[1])
    result["_row_study_id"] = result["_analysis_id"].astype(str).map(lambda value: source_meta.get(value, (None, ""))[0]).astype("Int64")
    return result


def materialize_dataset_row_provenance(
    project_id: int,
    dataset_ids: Iterable[int],
    *,
    sample_column: str | None = None,
    source_column: str | None = None,
    confirmed_samples: dict[str, int] | None = None,
    confirmed_sources: dict[str, int] | None = None,
) -> dict[str, int]:
    """Create row-level canonical links from staged columns after normal import.

    Similar-but-not-exact names are never silently merged. The caller must pass a
    confirmed mapping after showing reconciliation candidates to the user.
    """
    ensure_row_provenance_schema()
    sample_map = {str(k): int(v) for k, v in (confirmed_samples or {}).items()}
    source_map = {str(k): int(v) for k, v in (confirmed_sources or {}).items()}
    linked_samples = linked_sources = 0
    for dataset_id in dataset_ids:
        frame = load_dataset_dataframe(int(dataset_id), include_meta=True)
        if "_analysis_id" not in frame.columns:
            continue
        for _, row in frame.iterrows():
            analysis_id = str(row.get("_analysis_id") or "").strip()
            if not analysis_id:
                continue
            if sample_column and sample_column in frame.columns:
                label = str(row.get(sample_column) or "").strip()
                if label:
                    sample_id = canonical_sample_id(
                        int(project_id), label,
                        confirmed_existing_id=sample_map.get(label),
                    )
                    if sample_id is not None:
                        link_analysis_to_sample(analysis_id, sample_id, source_label=label)
                        linked_samples += 1
            if source_column and source_column in frame.columns:
                label = str(row.get(source_column) or "").strip()
                if label:
                    study_id = canonical_study_id(
                        int(project_id), label,
                        confirmed_existing_id=source_map.get(label),
                    )
                    if study_id is not None:
                        link_analysis_to_study(analysis_id, study_id, source_label=label)
                        linked_sources += 1
    return {"sample_links": linked_samples, "source_links": linked_sources}
