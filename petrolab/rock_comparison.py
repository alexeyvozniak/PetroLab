from __future__ import annotations

import pandas as pd

from petrolab.repositories.rock_repository import (
    composition_wide,
    get_composition,
    get_isotopes,
    isotope_wide,
    list_rocks,
)
from petrolab.rock_determinations import determination_dataframe


ROCK_SOURCE_COLUMN = "Источник данных"
ROCK_METHOD_COLUMN = "Метод химии"
ISOTOPE_METHOD_COLUMN = "Метод изотопии"


def _joined(values: list[str], empty: str) -> str:
    clean = [str(value).strip() for value in values if str(value).strip()]
    unique = list(dict.fromkeys(clean))
    return " | ".join(unique) if unique else empty


def _legacy_whole_rock_dataframe(project_id: int) -> pd.DataFrame:
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


def _determination_comparison_dataframe(project_id: int) -> pd.DataFrame:
    frame = determination_dataframe(int(project_id))
    if frame.empty:
        return frame
    result = frame.copy()
    result["_rock_id"] = pd.to_numeric(result["rock_id"], errors="coerce").astype("Int64")
    result["_determination_id"] = pd.to_numeric(result["id"], errors="coerce").astype("Int64")
    if "Rock" not in result.columns:
        result["Rock"] = result.get("Sample", "")
    result[ROCK_SOURCE_COLUMN] = result.get("Source", pd.Series("", index=result.index)).fillna("").astype(str)
    result[ROCK_SOURCE_COLUMN] = result[ROCK_SOURCE_COLUMN].replace("", "Свои / источник не указан")
    result[ROCK_METHOD_COLUMN] = result.get("Method", pd.Series("", index=result.index)).fillna("").astype(str)
    result[ROCK_METHOD_COLUMN] = result[ROCK_METHOD_COLUMN].replace("", "не указан")
    result["Лаборатория"] = result.get("laboratory", pd.Series("", index=result.index)).fillna("").astype(str)
    return result


def whole_rock_comparison_dataframe(project_id: int) -> pd.DataFrame:
    """One row per whole-rock determination, with legacy fallback for older samples.

    A physical rock sample may have multiple literature/laboratory determinations. New
    staging imports preserve each as a separate row, while pre-v0.15.4 records without
    determinations remain visible through the historical composition table.
    """
    legacy = _legacy_whole_rock_dataframe(int(project_id))
    determinations = _determination_comparison_dataframe(int(project_id))
    if determinations.empty:
        return legacy
    determination_rock_ids = {
        int(value) for value in determinations["_rock_id"].dropna().astype(int).tolist()
    }
    if legacy.empty:
        return determinations.reset_index(drop=True)
    remaining_legacy = legacy.loc[
        ~legacy["_rock_id"].astype(int).isin(determination_rock_ids)
    ].copy()
    return pd.concat([remaining_legacy, determinations], ignore_index=True, sort=False)


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
