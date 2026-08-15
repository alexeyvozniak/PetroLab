from __future__ import annotations

import pandas as pd

from petrolab.repositories.rock_repository import (
    composition_wide,
    get_composition,
    get_isotopes,
    isotope_wide,
    list_rocks,
)


ROCK_SOURCE_COLUMN = "Источник данных"
ROCK_METHOD_COLUMN = "Метод химии"
ISOTOPE_METHOD_COLUMN = "Метод изотопии"


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
    """Wide isotope data grouped by isotope-record provenance, not chemistry provenance."""
    frame = isotope_wide(int(project_id))
    if frame.empty:
        return frame
    metadata: dict[int, dict] = {}
    for rock in list_rocks(int(project_id)):
        rock_id = int(rock["id"])
        isotopes = get_isotopes(rock_id)
        if isotopes.empty:
            metadata[rock_id] = {
                ROCK_SOURCE_COLUMN: "Свои / источник не указан",
                ISOTOPE_METHOD_COLUMN: str(rock.get("isotope_method") or "не указан"),
                "Лаборатория": str(rock.get("laboratory") or ""),
            }
            continue
        metadata[rock_id] = {
            ROCK_SOURCE_COLUMN: _joined(
                isotopes.get("source", pd.Series(dtype=str)).fillna("").astype(str).tolist(),
                "Свои / источник не указан",
            ),
            ISOTOPE_METHOD_COLUMN: _joined(
                isotopes.get("method", pd.Series(dtype=str)).fillna("").astype(str).tolist(),
                str(rock.get("isotope_method") or "не указан"),
            ),
            "Лаборатория": _joined(
                isotopes.get("laboratory", pd.Series(dtype=str)).fillna("").astype(str).tolist(),
                str(rock.get("laboratory") or ""),
            ),
        }
    for column in (ROCK_SOURCE_COLUMN, ISOTOPE_METHOD_COLUMN, "Лаборатория"):
        frame[column] = [metadata.get(int(value), {}).get(column, "") for value in frame["_rock_id"]]
    return frame
