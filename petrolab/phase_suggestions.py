from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pandas as pd

from petrolab.db import _utcnow, connect
from petrolab.mineral_recognition_extended import (
    EXTENDED_RULESET_VERSION,
    recognize_dataframe_extended,
    recognize_mineral_extended,
    score_candidates_extended,
)

PHASE_SUGGESTION_RULESET_VERSION = EXTENDED_RULESET_VERSION
SUGGESTED_MINERAL_COLUMN = "Suggested Mineral"
SUGGESTION_CONFIDENCE_COLUMN = "Mineral suggestion confidence"
SUGGESTION_REASON_COLUMN = "Mineral suggestion reason"
SUGGESTION_RULESET_COLUMN = "Mineral suggestion ruleset"
_MIXED_SUFFIX = " · Неразобранные / mixed"
_RESOLVED_SUFFIX = " · Исходный mixed (разобрано)"

# `suggest_phase()` predates Mineral Recognition v1 and is retained as a broad-family compatibility
# API. Dataframe suggestions use the richer conservative chemical targets.
_LEGACY_BROAD_TARGETS = {
    "trioctahedral mica": "mica",
    "dioctahedral mica": "mica",
    "Li-mica": "mica",
    "calcic amphibole": "amphibole",
    "Ti-rich calcic amphibole": "amphibole",
    "sodic amphibole": "amphibole",
    "sodic-calcic amphibole": "amphibole",
    "K-feldspar": "feldspar",
    "plagioclase": "feldspar",
}

# Recognition labels are richer than the mineral-specific formula modules. Keep both:
# the exact phase label is used in the child dataset name, while `mineral_key` selects the
# safest available formula/QC module. Unknown or volatile/structure-dependent phases stay
# `generic` rather than being forced through an invalid structural formula.
_EXACT_STORAGE_KEYS = {
    "trioctahedral mica": "mica",
    "dioctahedral mica": "mica",
    "Li-mica": "mica",
    "calcic amphibole": "amphibole",
    "Ti-rich calcic amphibole": "amphibole",
    "sodic amphibole": "amphibole",
    "sodic-calcic amphibole": "amphibole",
    "K-feldspar": "feldspar",
    "plagioclase": "feldspar",
    "nepheline": "nepheline",
    "kalsilite": "feldspathoid",
    "leucite": "feldspathoid",
    "sodalite-group": "feldspathoid",
    "analcime": "feldspathoid",
    "olivine": "olivine",
    "monticellite": "olivine",
    "clinopyroxene": "clinopyroxene",
    "Na-Ca clinopyroxene": "clinopyroxene",
    "Na-clinopyroxene": "clinopyroxene",
    "orthopyroxene": "orthopyroxene",
    "low-Ca pyroxene": "orthopyroxene",
    "garnet": "garnet",
    "Ti-rich garnet": "garnet",
    "Ca-carbonate": "carbonate",
    "Ca-Mg carbonate": "carbonate",
    "Ca-Fe-Mg carbonate": "carbonate",
    "Mg-carbonate": "carbonate",
    "Fe-carbonate": "carbonate",
    "Mn-carbonate": "carbonate",
    "Sr-carbonate": "carbonate",
    "Sr-rich Ca carbonate": "carbonate",
    "Ba-rich Ca carbonate": "carbonate",
    "Cr-spinel": "spinel",
    "spinel-group oxide": "spinel",
    "Fe-Ti oxide": "fe_ti_oxide",
    "Fe-oxide": "spinel",
    "perovskite": "perovskite",
    "REE-Na titanate (loparite-type)": "perovskite",
    "apatite": "apatite",
    "titanite": "titanite",
    "zircon": "zircon",
}


def mineral_key_for_phase(phase_label: str) -> str:
    """Return the safest existing mineral module for a recognition/edited phase label."""
    clean = str(phase_label).strip()
    if clean in _EXACT_STORAGE_KEYS:
        return _EXACT_STORAGE_KEYS[clean]
    lowered = clean.casefold()
    if "mica" in lowered or "слюд" in lowered:
        return "mica"
    if "amphibol" in lowered or "амфиб" in lowered:
        return "amphibole"
    if "clinopyrox" in lowered or "клинопирокс" in lowered:
        return "clinopyroxene"
    if "orthopyrox" in lowered or "ортопирокс" in lowered:
        return "orthopyroxene"
    if "feldspar" in lowered or "полев" in lowered:
        return "feldspar"
    if "feldspath" in lowered or "nephe" in lowered or "sodal" in lowered or "leuc" in lowered:
        return "feldspathoid"
    if "garnet" in lowered or "гранат" in lowered:
        return "garnet"
    if "carbonate" in lowered or "карбонат" in lowered:
        return "carbonate"
    if "spinel" in lowered or "шпинел" in lowered or "chromite" in lowered:
        return "spinel"
    if "ilmen" in lowered or "fe-ti oxide" in lowered:
        return "fe_ti_oxide"
    if "perovsk" in lowered or "loparite" in lowered:
        return "perovskite"
    if "apatite" in lowered or "апатит" in lowered:
        return "apatite"
    if "titanite" in lowered or "титанит" in lowered:
        return "titanite"
    if "zircon" in lowered or "циркон" in lowered:
        return "zircon"
    if "oliv" in lowered or "олив" in lowered:
        return "olivine"
    return "generic"


def score_phase_candidates(row: Mapping[str, Any]) -> dict[str, tuple[float, list[str]]]:
    """Compatibility wrapper around the versioned extended Mineral Recognition engine."""
    return {
        name: (candidate.score, list(candidate.reasons))
        for name, candidate in score_candidates_extended(row).items()
    }


def suggest_phase(row: Mapping[str, Any]) -> tuple[str, str, str]:
    """Legacy broad-family suggestion API backed by the extended chemical recognizer."""
    result = recognize_mineral_extended(row)
    target = _LEGACY_BROAD_TARGETS.get(result.target, result.target)
    return target, result.confidence, "; ".join(result.reasons)


def attach_phase_suggestions(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Attach conservative extended targets; no mineral is ever confirmed automatically."""
    return recognize_dataframe_extended(dataframe)


def _copy_dataset_context(con, source_dataset_id: int, child_dataset_id: int) -> None:
    """Copy project/source/session memberships so split children stay visible everywhere."""
    has_links = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='project_dataset_links'"
    ).fetchone()
    if has_links:
        rows = con.execute(
            "SELECT project_id, note, purpose FROM project_dataset_links WHERE dataset_id=?",
            (int(source_dataset_id),),
        ).fetchall()
        con.executemany(
            """INSERT OR IGNORE INTO project_dataset_links(project_id, dataset_id, note, added_at, purpose)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (int(row["project_id"]), int(child_dataset_id), str(row["note"]), _utcnow(), str(row["purpose"]))
                for row in rows
            ],
        )

    has_sessions = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='analytical_session_datasets'"
    ).fetchone()
    if has_sessions:
        sessions = con.execute(
            "SELECT session_id FROM analytical_session_datasets WHERE dataset_id=?",
            (int(source_dataset_id),),
        ).fetchall()
        con.executemany(
            "INSERT OR IGNORE INTO analytical_session_datasets(session_id, dataset_id) VALUES (?, ?)",
            [(int(row["session_id"]), int(child_dataset_id)) for row in sessions],
        )

    has_studies = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='dataset_studies'"
    ).fetchone()
    if has_studies:
        studies = con.execute(
            "SELECT study_id, source_table, source_note FROM dataset_studies WHERE dataset_id=?",
            (int(source_dataset_id),),
        ).fetchall()
        con.executemany(
            """INSERT OR REPLACE INTO dataset_studies(dataset_id, study_id, source_table, source_note)
               VALUES (?, ?, ?, ?)""",
            [
                (int(child_dataset_id), row["study_id"], row["source_table"], row["source_note"])
                for row in studies
            ],
        )


def _root_dataset_name(name: str) -> str:
    clean = str(name)
    for suffix in (_MIXED_SUFFIX, _RESOLVED_SUFFIX):
        if clean.endswith(suffix):
            return clean[: -len(suffix)]
    return clean


def _existing_phase_dataset(con, source, child_name: str) -> int | None:
    """Find a previously created phase child from the same immutable source snapshot."""
    row = con.execute(
        """SELECT id FROM datasets
           WHERE id<>? AND project_id=? AND name=? AND source_filename=? AND source_sheet=? AND source_sha256=?
           ORDER BY id LIMIT 1""",
        (
            int(source["id"]), int(source["project_id"]), child_name,
            str(source["source_filename"]), str(source["source_sheet"]), str(source["source_sha256"]),
        ),
    ).fetchone()
    return int(row["id"]) if row else None


def materialize_confirmed_phases(source_dataset_id: int, assignments: Mapping[str, str]) -> dict[str, int]:
    """Move confirmed analyses from one mixed dataset into reusable child phase datasets.

    `assignments` values are human-readable phase labels, not necessarily PetroLab formula-module
    keys. Analysis IDs, source rows, point-image links and provenance remain intact. Child datasets
    inherit project/source/session membership. Unassigned analyses remain in the original dataset,
    which is labelled as unresolved/mixed. Repeated review reuses an existing phase child from the
    same source snapshot instead of creating duplicate datasets.
    """
    clean = {
        str(analysis_id).strip(): str(phase).strip()
        for analysis_id, phase in assignments.items()
        if str(analysis_id).strip() and str(phase).strip()
    }
    if not clean:
        return {}
    now = _utcnow()
    with connect() as con:
        source = con.execute("SELECT * FROM datasets WHERE id=?", (int(source_dataset_id),)).fetchone()
        if not source:
            raise ValueError("Исходный mixed dataset не найден")
        marks = ",".join("?" for _ in clean)
        rows = con.execute(
            f"SELECT analysis_id FROM analysis_rows WHERE dataset_id=? AND analysis_id IN ({marks})",
            [int(source_dataset_id), *clean.keys()],
        ).fetchall()
        existing = {str(row["analysis_id"]) for row in rows}
        missing = [analysis_id for analysis_id in clean if analysis_id not in existing]
        if missing:
            raise ValueError("Некоторые анализы не принадлежат исходному mixed dataset")

        columns = [
            str(row[1]) for row in con.execute("PRAGMA table_info(datasets)").fetchall()
            if str(row[1]) != "id"
        ]
        root_name = _root_dataset_name(str(source["name"]))
        created: dict[str, int] = {}
        for phase_label in sorted(set(clean.values()), key=str.casefold):
            child_name = f"{root_name} · {phase_label}"
            child_id = _existing_phase_dataset(con, source, child_name)
            if child_id is None:
                values = {column: source[column] for column in columns}
                values["name"] = child_name
                values["mineral_key"] = mineral_key_for_phase(phase_label)
                values["row_count"] = 0
                values["imported_at"] = now
                placeholders = ",".join("?" for _ in columns)
                cur = con.execute(
                    f"INSERT INTO datasets({','.join(columns)}) VALUES ({placeholders})",
                    [values[column] for column in columns],
                )
                child_id = int(cur.lastrowid)
                _copy_dataset_context(con, int(source_dataset_id), child_id)
            created[phase_label] = int(child_id)

        for phase_label, child_id in created.items():
            ids = [analysis_id for analysis_id, assigned in clean.items() if assigned == phase_label]
            marks = ",".join("?" for _ in ids)
            con.execute(
                f"UPDATE analysis_rows SET dataset_id=? WHERE dataset_id=? AND analysis_id IN ({marks})",
                [int(child_id), int(source_dataset_id), *ids],
            )
            moved = con.execute(
                "SELECT analysis_id FROM analysis_rows WHERE dataset_id=? ORDER BY source_row, analysis_id",
                (int(child_id),),
            ).fetchall()
            con.executemany(
                "UPDATE analysis_rows SET row_index=? WHERE analysis_id=?",
                [(index, row["analysis_id"]) for index, row in enumerate(moved)],
            )
            con.execute("UPDATE datasets SET row_count=? WHERE id=?", (len(moved), int(child_id)))

        remaining = con.execute(
            "SELECT analysis_id FROM analysis_rows WHERE dataset_id=? ORDER BY source_row, analysis_id",
            (int(source_dataset_id),),
        ).fetchall()
        con.executemany(
            "UPDATE analysis_rows SET row_index=? WHERE analysis_id=?",
            [(index, row["analysis_id"]) for index, row in enumerate(remaining)],
        )
        source_name = f"{root_name}{_MIXED_SUFFIX}" if remaining else f"{root_name}{_RESOLVED_SUFFIX}"
        con.execute(
            "UPDATE datasets SET row_count=?, name=? WHERE id=?",
            (len(remaining), source_name, int(source_dataset_id)),
        )
        con.commit()
    return created
