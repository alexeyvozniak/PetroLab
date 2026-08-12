from __future__ import annotations

import hashlib
import json
import math
import unicodedata
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping

import pandas as pd

IDENTITY_STRATEGIES: tuple[tuple[str, ...], ...] = (
    ("Sample", "Grain", "Point"),
    ("Sample", "Point"),
    ("Grain", "Point"),
    ("Point",),
)

# Values produced by PetroLab itself must not make a raw-row fingerprint unstable.
_DERIVED_PREFIXES = (
    "apfu_", "QC ", "Mg#", "Fe3+", "Wo", "En", "Fs", "Fo", "Fa", "Te",
    "Prp", "Alm", "Sps", "Grs", "Adr", "Uv", "Endmember_", "Ne", "Ks", "CaNe",
    "Qxs", "KsM", "T_sum", "cavity_", "Delta", "Δ", "Si/Al", "OH_",
)
_DERIVED_EXACT = {"Σ оксидов"}


@dataclass(frozen=True)
class ExistingAnalysis:
    analysis_id: str
    source_row: int | None
    data: Mapping[str, object]


@dataclass(frozen=True)
class AnalysisMatchResult:
    matched_ids: Mapping[int, str]
    strategies: Mapping[int, str]
    moved_rows_detected: bool
    unmatched_existing_ids: frozenset[str]


def match_existing_analyses(
    existing: Iterable[ExistingAnalysis],
    new_dataframe: pd.DataFrame,
    source_rows: list[int | None],
) -> AnalysisMatchResult:
    """Match refreshed rows to old analysis IDs without guessing through ambiguity.

    Semantic keys are used only when unique on both sides. Exact row fingerprints then
    recover rows that were sorted without identifiers. Source-row fallback is allowed only
    when row count is unchanged and there is no evidence of row movement.
    """
    old = list(existing)
    if len(source_rows) != len(new_dataframe):
        raise ValueError("Количество source_rows не совпадает с числом новых строк")

    new_records = [row.to_dict() for _, row in new_dataframe.iterrows()]
    matched: dict[int, str] = {}
    strategies: dict[int, str] = {}
    used_old: set[str] = set()
    # An insertion/deletion alone makes physical row numbers unsafe, even if all values
    # were edited at the same time and movement cannot be demonstrated by fingerprints.
    moved = len(old) != len(new_records)

    for fields in IDENTITY_STRATEGIES:
        old_keys = [_semantic_key(item.data, fields) for item in old]
        new_keys = [_semantic_key(record, fields) for record in new_records]
        old_counts = Counter(key for key in old_keys if key is not None)
        new_counts = Counter(key for key in new_keys if key is not None)
        old_by_key = {
            key: item
            for item, key in zip(old, old_keys)
            if key is not None and old_counts[key] == 1
        }
        for index, key in enumerate(new_keys):
            if index in matched or key is None or new_counts[key] != 1:
                continue
            item = old_by_key.get(key)
            if item is None or item.analysis_id in used_old:
                continue
            matched[index] = item.analysis_id
            strategies[index] = "+".join(fields)
            used_old.add(item.analysis_id)
            if item.source_row is not None and source_rows[index] is not None and item.source_row != source_rows[index]:
                moved = True

    # Exact fingerprints are deliberately based on source-like values and ignore common
    # calculated columns. They are useful for reordered rows even when semantic IDs are absent.
    old_fp = [_row_fingerprint(item.data) for item in old]
    new_fp = [_row_fingerprint(record) for record in new_records]
    old_counts = Counter(old_fp)
    new_counts = Counter(new_fp)
    old_by_fp = {
        fp: item for item, fp in zip(old, old_fp)
        if old_counts[fp] == 1
    }
    for index, fp in enumerate(new_fp):
        if index in matched or new_counts[fp] != 1:
            continue
        item = old_by_fp.get(fp)
        if item is None or item.analysis_id in used_old:
            continue
        matched[index] = item.analysis_id
        strategies[index] = "exact-row"
        used_old.add(item.analysis_id)
        if item.source_row is not None and source_rows[index] is not None and item.source_row != source_rows[index]:
            moved = True

    # Reusing a row number after an insertion/sort can silently attach an image to the
    # wrong analysis. Positional fallback is therefore deliberately conservative.
    if not moved:
        old_by_source = {
            item.source_row: item
            for item in old
            if item.source_row is not None and item.analysis_id not in used_old
        }
        for index, source_row in enumerate(source_rows):
            if index in matched or source_row is None:
                continue
            item = old_by_source.get(source_row)
            if item is None or item.analysis_id in used_old:
                continue
            if _semantic_conflict(item.data, new_records[index]):
                continue
            matched[index] = item.analysis_id
            strategies[index] = "source-row"
            used_old.add(item.analysis_id)

    all_old = {item.analysis_id for item in old}
    return AnalysisMatchResult(
        matched_ids=matched,
        strategies=strategies,
        moved_rows_detected=moved,
        unmatched_existing_ids=frozenset(all_old - used_old),
    )


def _semantic_key(record: Mapping[str, object], fields: tuple[str, ...]) -> tuple[str, ...] | None:
    values: list[str] = []
    for field in fields:
        value = _stable_scalar(record.get(field))
        if value is None:
            return None
        values.append(value)
    return tuple(values)


def _semantic_conflict(old: Mapping[str, object], new: Mapping[str, object]) -> bool:
    for fields in IDENTITY_STRATEGIES:
        old_key = _semantic_key(old, fields)
        new_key = _semantic_key(new, fields)
        if old_key is not None and new_key is not None:
            return old_key != new_key
    return False


def _row_fingerprint(record: Mapping[str, object]) -> str:
    payload: list[tuple[str, str | None]] = []
    for key in sorted(str(k) for k in record):
        if key.startswith("_") or key in _DERIVED_EXACT or key.startswith(_DERIVED_PREFIXES):
            continue
        payload.append((key, _stable_scalar(record.get(key))))
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _stable_scalar(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        numeric = float(value)
        if math.isnan(numeric):
            return None
        return format(numeric, ".12g")
    text = unicodedata.normalize("NFKC", str(value)).strip()
    return text.casefold() if text else None
