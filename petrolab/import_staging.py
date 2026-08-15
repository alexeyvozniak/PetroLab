from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata
from typing import Iterable, Mapping

import pandas as pd


ROLE_ALIASES: dict[str, tuple[str, ...]] = {
    "Sample": (
        "sample", "sample id", "sample_id", "specimen", "образец", "номер образца", "проба", "sample no",
    ),
    "Lithology": (
        "lithology", "rock", "rock type", "rock_type", "rock name", "порода", "литология", "тип породы",
    ),
    "Source": (
        "source", "reference", "references", "ref", "citation", "literature", "article", "study",
        "источник", "ссылка", "литература", "статья",
    ),
    "Mineral": ("mineral", "phase", "минерал", "фаза"),
    "Generation": ("generation", "gen", "group", "поколение", "генерация", "группа"),
    "Grain": ("grain", "grain id", "grain_id", "зерно", "номер зерна"),
    "Point": ("point", "spot", "analysis", "analysis id", "точка", "точка анализа", "анализ"),
    "Method": ("method", "analytical method", "technique", "метод", "метод анализа"),
    "Laboratory": ("laboratory", "lab", "laboratory name", "лаборатория", "лаборатория анализа"),
    "Locality": ("locality", "location", "местоположение", "участок", "локалитет"),
    "Massif": ("massif", "complex", "intrusion", "массив", "комплекс", "интрузия"),
    "Latitude": ("latitude", "lat", "широта", "широта град"),
    "Longitude": ("longitude", "lon", "long", "долгота", "долгота град"),
    "Age": ("age", "age ma", "age (ma)", "age, ma", "возраст", "возраст млн лет", "возраст, млн лет"),
    "Age uncertainty": (
        "age uncertainty", "age error", "age err", "age +/-", "age ±", "ошибка возраста", "погрешность возраста", "± млн лет",
    ),
    "Age method": ("age method", "dating method", "geochronology", "метод возраста", "метод датирования"),
}

_RU_TO_LAT = {
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i","й":"i",
    "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f",
    "х":"kh","ц":"ts","ч":"ch","ш":"sh","щ":"shch","ъ":"","ы":"y","ь":"","э":"e","ю":"yu","я":"ya",
}


def _plain(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    text = text.replace("ё", "е")
    text = re.sub(r"[\s_\-–—./\\()\[\],;:]+", "", text)
    return "".join(ch for ch in text if ch.isalnum())


def transliteration_key(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    transliterated = "".join(_RU_TO_LAT.get(ch, ch) for ch in text)
    return _plain(transliterated)


def normalized_name_key(value: object) -> str:
    """Loose phonetic key used only to *suggest* aliases, never to merge automatically.

    Small English/Russian spelling differences common in geological terminology are
    intentionally collapsed here (ph/f, c/k and a final silent e). Because this key
    is suggestion-only, a false positive still requires an explicit user confirmation.
    """
    key = transliteration_key(value)
    key = key.replace("ph", "f").replace("ck", "k").replace("c", "k")
    if len(key) > 5 and key.endswith("e"):
        key = key[:-1]
    return key


def name_similarity(left: object, right: object) -> float:
    a, b = normalized_name_key(left), normalized_name_key(right)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


@dataclass(frozen=True)
class SimilarName:
    incoming: str
    existing: str
    score: float
    reason: str


def similar_name_candidates(
    incoming: Iterable[str],
    existing: Iterable[str],
    *,
    threshold: float = 0.90,
) -> list[SimilarName]:
    """Find likely aliases without flooding short scientific IDs with false matches."""
    result: list[SimilarName] = []
    seen: set[tuple[str, str]] = set()
    existing_clean = [str(value).strip() for value in existing if str(value).strip()]
    for raw in incoming:
        candidate = str(raw).strip()
        if not candidate:
            continue
        for current in existing_clean:
            if candidate == current:
                continue
            score = name_similarity(candidate, current)
            if score < threshold:
                continue
            pair = (candidate.casefold(), current.casefold())
            if pair in seen:
                continue
            seen.add(pair)
            if candidate.casefold() == current.casefold():
                reason = "отличается только регистром"
            elif normalized_name_key(candidate) == normalized_name_key(current):
                reason = "совпадает после нормализации/транслитерации"
            else:
                reason = "похожее написание"
            result.append(SimilarName(candidate, current, float(score), reason))
    return sorted(result, key=lambda item: (-item.score, item.incoming.casefold(), item.existing.casefold()))


def detect_role_columns(columns: Iterable[object]) -> dict[str, str]:
    normalized = {str(column): _plain(column) for column in columns}
    suggestions: dict[str, str] = {}
    for role, aliases in ROLE_ALIASES.items():
        alias_keys = {_plain(alias) for alias in aliases}
        exact = [column for column, key in normalized.items() if key in alias_keys]
        if exact:
            suggestions[role] = exact[0]
            continue
        fuzzy: list[tuple[float, str]] = []
        for column, key in normalized.items():
            if not key:
                continue
            best = max((SequenceMatcher(None, key, alias).ratio() for alias in alias_keys), default=0.0)
            if best >= 0.88:
                fuzzy.append((best, column))
        if fuzzy:
            suggestions[role] = max(fuzzy)[1]
    return suggestions


def source_like_column(dataframe: pd.DataFrame) -> str | None:
    return detect_role_columns(dataframe.columns).get("Source")


def _nonempty_count(row: pd.Series) -> int:
    count = 0
    for value in row.tolist():
        if pd.isna(value):
            continue
        if str(value).strip():
            count += 1
    return count


def detect_block_header_rows(
    dataframe: pd.DataFrame,
    *,
    chemistry_columns: Iterable[str] | None = None,
) -> list[tuple[int, str]]:
    """Conservative block-header suggestions for literature tables.

    A row is only suggested when it has one visible textual value and no numeric
    chemistry. It is never applied automatically; the staging UI asks the user what
    that value means (Sample, Lithology, Source, Locality, custom field, or ignore).
    """
    chemistry = [str(column) for column in (chemistry_columns or []) if str(column) in dataframe.columns]
    suggestions: list[tuple[int, str]] = []
    for position, (_, row) in enumerate(dataframe.iterrows()):
        if _nonempty_count(row) != 1:
            continue
        if chemistry:
            numeric = pd.to_numeric(row[chemistry], errors="coerce")
            if numeric.notna().any():
                continue
        values = [str(value).strip() for value in row.tolist() if pd.notna(value) and str(value).strip()]
        if not values:
            continue
        text = values[0]
        if len(text) > 120:
            continue
        suggestions.append((position, text))
    return suggestions


def assign_value_to_rows(
    dataframe: pd.DataFrame,
    rows: Iterable[int],
    *,
    field: str,
    value: object,
) -> pd.DataFrame:
    result = dataframe.copy()
    if field not in result.columns:
        result[field] = pd.NA
    valid = [int(position) for position in rows if 0 <= int(position) < len(result)]
    if valid:
        column_index = result.columns.get_loc(field)
        for position in valid:
            result.iat[position, column_index] = value
    return result


def apply_block_fill(
    dataframe: pd.DataFrame,
    headers: Mapping[int, str],
    *,
    field: str,
    drop_header_rows: bool = True,
) -> pd.DataFrame:
    """Fill values from confirmed block headers down to the next confirmed header."""
    result = dataframe.copy()
    if field not in result.columns:
        result[field] = pd.NA
    ordered = sorted((int(position), str(value)) for position, value in headers.items())
    for index, (start, value) in enumerate(ordered):
        stop = ordered[index + 1][0] if index + 1 < len(ordered) else len(result)
        first_data = start + 1 if drop_header_rows else start
        if first_data < stop:
            result = assign_value_to_rows(result, range(first_data, stop), field=field, value=value)
    if drop_header_rows and ordered:
        result = result.drop(result.index[[position for position, _ in ordered]]).reset_index(drop=True)
    return result


def split_by_column(dataframe: pd.DataFrame, column: str) -> dict[str, pd.DataFrame]:
    if column not in dataframe.columns:
        return {}
    result: dict[str, pd.DataFrame] = {}
    values = dataframe[column].fillna("").astype(str).str.strip()
    for value in sorted({item for item in values if item}, key=str.casefold):
        result[value] = dataframe.loc[values == value].copy().reset_index(drop=True)
    return result
