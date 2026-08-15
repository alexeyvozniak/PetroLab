from __future__ import annotations

import pandas as pd

from petrolab.repositories.rock_repository import composition_wide, get_composition, isotope_wide, list_rocks


ROCK_SOURCE_COLUMN = "Источник данных"
ROCK_METHOD_COLUMN = "Метод химии"


def _joined(values: list[str], empty: str) -> str:
    clean = [str(value).strip() for value in values if str(value).strip()]
    unique = list(dict.fromkeys(clean))
    return " | ".join(unique) if unique else empty


def whole_rock_comparison_dataframe(project_id: int) -> pd.DataFrame:
    """Wide whole-rock chemistry with source/method metadata preserved for grouping."""
    wide = composition_wide(int(project_id))
    if wide.empty:
        return wide
    metadata: dict[int, dict] = {}
    for rock in list_rocks(int(project_id)):
        rock_id = int(rock["id"])
        comp = get_composition(rock_id)
        metadata[rock_id] = {
            ROCK_SOURCE_COLUMN: _joined(
                comp.get("source", pd.Series(dtype=str)).fillna("").astype(str).tolist(),
                "Свои / источник не указан",
            ),
            ROCK_METHOD_COLUMN: _joined(
                comp.get("method", pd.Series(dtype=str)).fillna("").astype(str).tolist(),
                str(rock.get("chemistry_method") or "не указан"),
            ),
            "Лаборатория": str(rock.get("laboratory") or ""),
        }
    for column in (ROCK_SOURCE_COLUMN, ROCK_METHOD_COLUMN, "Лаборатория"):
        wide[column] = [metadata.get(int(value), {}).get(column, "") for value in wide["_rock_id"]]
    return wide


def whole_rock_isotope_comparison_dataframe(project_id: int) -> pd.DataFrame:
    frame = isotope_wide(int(project_id))
    if frame.empty:
        return frame
    # isotope_wide already keeps one row per rock. Source provenance remains in the long
    # isotope table; grouping by chemistry source is useful for study-level comparisons.
    chemistry = whole_rock_comparison_dataframe(int(project_id))
    if not chemistry.empty and "_rock_id" in frame.columns and "_rock_id" in chemistry.columns:
        meta = chemistry[["_rock_id", ROCK_SOURCE_COLUMN, ROCK_METHOD_COLUMN]].drop_duplicates("_rock_id")
        frame = frame.merge(meta, on="_rock_id", how="left")
    return frame
