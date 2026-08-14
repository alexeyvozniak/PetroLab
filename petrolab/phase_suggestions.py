from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from typing import Any

import numpy as np
import pandas as pd

from petrolab.db import _utcnow, connect

SUGGESTED_MINERAL_COLUMN = "Suggested Mineral"
SUGGESTION_CONFIDENCE_COLUMN = "Mineral suggestion confidence"
SUGGESTION_REASON_COLUMN = "Mineral suggestion reason"


def _value(row: Mapping[str, Any], key: str) -> float:
    try:
        value = float(row.get(key, np.nan))
    except (TypeError, ValueError):
        return float("nan")
    return value if np.isfinite(value) else float("nan")


def _sum(row: Mapping[str, Any], *keys: str) -> float:
    values = [_value(row, key) for key in keys]
    return float(sum(value for value in values if np.isfinite(value)))


def _between(value: float, low: float, high: float) -> bool:
    return np.isfinite(value) and low <= value <= high


def _lt(value: float, limit: float) -> bool:
    return np.isfinite(value) and value < limit


def _gt(value: float, limit: float) -> bool:
    return np.isfinite(value) and value > limit


def score_phase_candidates(row: Mapping[str, Any]) -> dict[str, tuple[float, list[str]]]:
    """Return conservative broad-phase scores for common EPMA mineral analyses.

    These are suggestions only. Rules intentionally favour high-specificity signatures and
    leave overlapping silicates unresolved rather than pretending to provide IMA classification.
    """
    sio2 = _value(row, "SiO2")
    tio2 = _value(row, "TiO2")
    al2o3 = _value(row, "Al2O3")
    cr2o3 = _value(row, "Cr2O3")
    feo = _sum(row, "FeO", "FeOt")
    fe2o3 = _sum(row, "Fe2O3", "Fe2O3t")
    mgo = _value(row, "MgO")
    cao = _value(row, "CaO")
    na2o = _value(row, "Na2O")
    k2o = _value(row, "K2O")
    p2o5 = _value(row, "P2O5")
    zro2 = _value(row, "ZrO2")

    scores: dict[str, list[Any]] = defaultdict(lambda: [0.0, []])

    def add(key: str, points: float, reason: str) -> None:
        scores[key][0] += float(points)
        scores[key][1].append(reason)

    # Highly diagnostic accessory/oxide phases first.
    if _gt(p2o5, 20) and _gt(cao, 20):
        add("apatite", 6, "high P2O5 + CaO")
    if _gt(zro2, 30) and _between(sio2, 10, 45):
        add("zircon", 7, "high ZrO2 with silicate component")
    if _gt(tio2, 30) and _gt(cao, 20) and (not np.isfinite(sio2) or sio2 < 15):
        add("perovskite", 7, "TiO2- and CaO-rich, Si-poor")
    if _between(tio2, 20, 50) and _between(cao, 15, 35) and _between(sio2, 20, 45):
        add("titanite", 6, "Ti-Ca silicate signature")
    if (not np.isfinite(sio2) or sio2 < 8) and _sum(row, "Al2O3", "Cr2O3", "FeO", "FeOt", "Fe2O3", "Fe2O3t") > 45:
        add("spinel", 5, "Si-poor Al/Cr/Fe oxide")
    if _gt(tio2, 25) and (not np.isfinite(sio2) or sio2 < 8) and _sum(row, "FeO", "FeOt", "Fe2O3", "Fe2O3t") > 20:
        add("fe_ti_oxide", 6, "Ti-Fe oxide signature")
    if (not np.isfinite(sio2) or sio2 < 12) and _sum(row, "CaO", "MgO", "FeO", "FeOt", "MnO") > 40 and (not np.isfinite(al2o3) or al2o3 < 8):
        add("carbonate", 5, "Si-poor Ca-Mg-Fe composition")

    # Framework silicates.
    alkalis = _sum(row, "Na2O", "K2O")
    if _between(sio2, 55, 75) and _between(al2o3, 12, 28) and alkalis + (cao if np.isfinite(cao) else 0) > 7:
        add("feldspar", 5, "Si-Al framework silicate with Na-K-Ca")
    if _between(sio2, 35, 50) and _between(al2o3, 20, 40) and alkalis > 12:
        add("nepheline", 6, "Si-poor Al-rich alkali feldspathoid signature")

    # Mafic silicates. Rules are deliberately conservative where amphibole/cpx overlap.
    mafic = _sum(row, "MgO", "FeO", "FeOt")
    if _between(sio2, 30, 45) and mafic > 35 and (not np.isfinite(cao) or cao < 6) and (not np.isfinite(al2o3) or al2o3 < 6):
        add("olivine", 6, "Mg-Fe rich low-Al low-Ca silicate")
    if _between(sio2, 45, 58) and _between(cao, 10, 28) and mafic > 8 and (not np.isfinite(k2o) or k2o < 2):
        add("clinopyroxene", 4, "Ca-Mg-Fe pyroxene-like composition")
    if _between(sio2, 45, 60) and mafic > 20 and (not np.isfinite(cao) or cao < 5) and (not np.isfinite(na2o) or na2o < 2):
        add("orthopyroxene", 4, "low-Ca Mg-Fe pyroxene-like composition")
    if _between(sio2, 38, 55) and _between(al2o3, 5, 20) and _between(cao, 8, 16) and _sum(row, "Na2O", "K2O") > 1.5 and mafic > 8:
        add("amphibole", 3.5, "Ca-Na-K-bearing mafic silicate; amphibole/cpx overlap possible")
    if _between(sio2, 25, 50) and _gt(k2o, 5) and _between(al2o3, 5, 25) and mafic > 5:
        add("mica", 6, "K-rich Al-bearing mafic sheet silicate")
    if _between(sio2, 30, 45) and _sum(row, "Al2O3", "Fe2O3", "Fe2O3t", "TiO2", "Cr2O3") > 10 and _sum(row, "CaO", "MgO", "FeO", "FeOt", "MnO") > 20 and alkalis < 4:
        add("garnet", 4.5, "alkali-poor divalent + trivalent silicate balance")

    return {key: (float(value[0]), list(value[1])) for key, value in scores.items() if value[0] > 0}


def suggest_phase(row: Mapping[str, Any]) -> tuple[str, str, str]:
    scores = score_phase_candidates(row)
    if not scores:
        return "", "unresolved", "no sufficiently diagnostic rule matched"
    ranked = sorted(scores.items(), key=lambda item: item[1][0], reverse=True)
    best_name, (best_score, reasons) = ranked[0]
    second_score = ranked[1][1][0] if len(ranked) > 1 else 0.0
    margin = best_score - second_score
    # High confidence requires a specific score and meaningful separation.
    if best_score >= 6 and margin >= 2:
        confidence = "high"
    elif best_score >= 4.5 and margin >= 1.5:
        confidence = "medium"
    else:
        return "", "ambiguous", "; ".join(reasons + ([f"competing candidate: {ranked[1][0]}" ] if len(ranked) > 1 else []))
    return best_name, confidence, "; ".join(reasons)


def attach_phase_suggestions(dataframe: pd.DataFrame) -> pd.DataFrame:
    out = dataframe.copy()
    suggestions = [suggest_phase(row) for row in out.to_dict(orient="records")]
    out[SUGGESTED_MINERAL_COLUMN] = [item[0] for item in suggestions]
    out[SUGGESTION_CONFIDENCE_COLUMN] = [item[1] for item in suggestions]
    out[SUGGESTION_REASON_COLUMN] = [item[2] for item in suggestions]
    return out


def materialize_confirmed_phases(source_dataset_id: int, assignments: Mapping[str, str]) -> dict[str, int]:
    """Move confirmed analyses from one mixed dataset into child mineral datasets.

    Analysis IDs, data_json, source row, image links and provenance remain intact. No rows are
    duplicated. Unassigned analyses stay in the source dataset.
    """
    clean = {str(analysis_id).strip(): str(mineral).strip() for analysis_id, mineral in assignments.items() if str(analysis_id).strip() and str(mineral).strip()}
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

        columns = [str(row[1]) for row in con.execute("PRAGMA table_info(datasets)").fetchall() if str(row[1]) != "id"]
        created: dict[str, int] = {}
        for mineral in sorted(set(clean.values())):
            values = {column: source[column] for column in columns}
            values["name"] = f"{source['name']} · {mineral}"
            values["mineral_key"] = mineral
            values["row_count"] = 0
            values["imported_at"] = now
            placeholders = ",".join("?" for _ in columns)
            cur = con.execute(
                f"INSERT INTO datasets({','.join(columns)}) VALUES ({placeholders})",
                [values[column] for column in columns],
            )
            child_id = int(cur.lastrowid)
            created[mineral] = child_id
            # Preserve Study/Source provenance when present.
            study = con.execute("SELECT study_id, source_table, source_note FROM dataset_studies WHERE dataset_id=?", (int(source_dataset_id),)).fetchone() if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dataset_studies'").fetchone() else None
            if study:
                con.execute(
                    "INSERT OR REPLACE INTO dataset_studies(dataset_id, study_id, source_table, source_note) VALUES (?, ?, ?, ?)",
                    (child_id, study["study_id"], study["source_table"], study["source_note"]),
                )

        for mineral, child_id in created.items():
            ids = [analysis_id for analysis_id, assigned in clean.items() if assigned == mineral]
            marks = ",".join("?" for _ in ids)
            con.execute(
                f"UPDATE analysis_rows SET dataset_id=? WHERE dataset_id=? AND analysis_id IN ({marks})",
                [child_id, int(source_dataset_id), *ids],
            )
            moved = con.execute("SELECT analysis_id FROM analysis_rows WHERE dataset_id=? ORDER BY source_row, analysis_id", (child_id,)).fetchall()
            con.executemany("UPDATE analysis_rows SET row_index=? WHERE analysis_id=?", [(index, row["analysis_id"]) for index, row in enumerate(moved)])
            con.execute("UPDATE datasets SET row_count=? WHERE id=?", (len(moved), child_id))

        remaining = con.execute("SELECT analysis_id FROM analysis_rows WHERE dataset_id=? ORDER BY source_row, analysis_id", (int(source_dataset_id),)).fetchall()
        con.executemany("UPDATE analysis_rows SET row_index=? WHERE analysis_id=?", [(index, row["analysis_id"]) for index, row in enumerate(remaining)])
        con.execute("UPDATE datasets SET row_count=? WHERE id=?", (len(remaining), int(source_dataset_id)))
        con.commit()
    return created
