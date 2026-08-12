from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Mapping

import pandas as pd

CANONICAL_ROLES = ("Sample", "Grain", "Point", "Generation")

# These aliases are intentionally conservative. Ambiguous labels such as Group/Type
# are not silently converted to Generation; the import UI may suggest them for review.
SEMANTIC_ALIASES: dict[str, set[str]] = {
    "Sample": {
        "sample", "sampleid", "sampleno", "samplenumber", "образец", "образецid",
        "обр", "номеробразца", "sample_id", "sample_no",
    },
    "Grain": {
        "grain", "grainid", "grainno", "grainnumber", "зерно", "зерноid",
        "номерзерна", "grain_id", "grain_no",
    },
    "Point": {
        "point", "pointid", "pointno", "spot", "spotid", "analysis", "analysisno",
        "точка", "точкаанализа", "номерточки", "point_id", "spot_id",
    },
    "Generation": {
        "generation", "generationid", "gen", "genid", "gener", "поколение",
        "генерация", "ген", "generation_id", "gen_id",
    },
}

WEAK_ROLE_CANDIDATES: dict[str, set[str]] = {
    "Generation": {"group", "type", "zone", "rimcore", "population", "series"},
}

OXIDE_ALIASES: dict[str, str] = {
    "sio2": "SiO2",
    "tio2": "TiO2",
    "al2o3": "Al2O3",
    "cr2o3": "Cr2O3",
    "fe2o3": "Fe2O3",
    "feo": "FeO",
    "feot": "FeO",
    "feotot": "FeO",
    "feototal": "FeO",
    "totalfeasfeo": "FeO",
    "feo*": "FeO",
    "mno": "MnO",
    "mgo": "MgO",
    "cao": "CaO",
    "na2o": "Na2O",
    "k2o": "K2O",
    "p2o5": "P2O5",
    "nio": "NiO",
    "bao": "BaO",
    "sro": "SrO",
    "zno": "ZnO",
    "v2o3": "V2O3",
    "v2o5": "V2O5",
    "zro2": "ZrO2",
    "hfo2": "HfO2",
    "nb2o5": "Nb2O5",
    "ta2o5": "Ta2O5",
    "la2o3": "La2O3",
    "ce2o3": "Ce2O3",
    "nd2o3": "Nd2O3",
    "y2o3": "Y2O3",
    "tho2": "ThO2",
    "uo2": "UO2",
    "so3": "SO3",
    "h2o": "H2O",
    "f": "F",
    "cl": "Cl",
}

_UNIT_SUFFIX_RE = re.compile(
    r"[\s,;:_-]*(?:\(|\[)?\s*(?:wt\.?\s*%|wtpct|mass\s*%|мас\.?\s*%|weight\s*%)\s*(?:\)|\])?$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class SheetSchema:
    """Detected semantic roles for one imported sheet."""

    columns: tuple[str, ...]
    suggested: Mapping[str, str]
    weak_candidates: Mapping[str, tuple[str, ...]]


def _nfkc(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value)).strip()


def _token(value: object) -> str:
    text = _nfkc(value).lower()
    text = _UNIT_SUFFIX_RE.sub("", text)
    text = text.replace("ё", "е")
    text = re.sub(r"[\s._\-/()\[\]{},;:%]+", "", text)
    return text


_SEMANTIC_TOKENS = {
    role: {_token(alias) for alias in aliases}
    for role, aliases in SEMANTIC_ALIASES.items()
}
_WEAK_TOKENS = {
    role: {_token(alias) for alias in aliases}
    for role, aliases in WEAK_ROLE_CANDIDATES.items()
}


def canonicalize_header(value: object) -> str:
    """Normalize known oxide headers while preserving unknown scientific columns."""
    original = _nfkc(value)
    token = _token(original)
    return OXIDE_ALIASES.get(token, original)


def infer_semantic_mapping(columns: Iterable[object]) -> dict[str, str]:
    """Return only high-confidence semantic column mappings."""
    result: dict[str, str] = {}
    for column in columns:
        token = _token(column)
        for role, aliases in _SEMANTIC_TOKENS.items():
            if token in aliases and role not in result:
                result[role] = str(column)
                break
    return result


def inspect_sheet_schema(columns: Iterable[object]) -> SheetSchema:
    names = tuple(str(column) for column in columns)
    suggested = infer_semantic_mapping(names)
    weak: dict[str, tuple[str, ...]] = {}
    for role, aliases in _WEAK_TOKENS.items():
        candidates = [name for name in names if _token(name) in aliases]
        if candidates:
            weak[role] = tuple(candidates)
    return SheetSchema(columns=names, suggested=suggested, weak_candidates=weak)


def validate_semantic_mapping(columns: Iterable[str], semantic_map: Mapping[str, str] | None) -> dict[str, str]:
    """Validate user-confirmed semantic roles against one sheet's normalized headers."""
    available = {str(column) for column in columns}
    clean: dict[str, str] = {}
    used_sources: set[str] = set()
    for role, source in (semantic_map or {}).items():
        if role not in CANONICAL_ROLES or not source:
            continue
        source = str(source)
        if source not in available:
            raise ValueError(f"Колонка «{source}» для роли {role} отсутствует на листе")
        if source in used_sources:
            raise ValueError(f"Колонка «{source}» назначена сразу нескольким ролям")
        if role in available and source != role:
            raise ValueError(f"На листе уже существует каноническая колонка {role}")
        clean[role] = source
        used_sources.add(source)
    return clean


def apply_semantic_mapping(
    dataframe: pd.DataFrame,
    column_map: dict[str, dict],
    semantic_map: Mapping[str, str] | None,
) -> tuple[pd.DataFrame, dict[str, dict], dict[str, str]]:
    """Rename confirmed semantic columns without losing their Excel origin mapping."""
    clean = validate_semantic_mapping(dataframe.columns, semantic_map)
    if not clean:
        return dataframe.copy(), dict(column_map), {}

    rename_map = {source: role for role, source in clean.items() if source != role}
    out = dataframe.rename(columns=rename_map).copy()
    mapped = dict(column_map)
    for source, role in rename_map.items():
        info = dict(mapped.pop(source))
        info["normalized_from"] = source
        mapped[role] = info
    mapped["__schema__"] = {"semantic": clean}
    return out, mapped, clean


def stored_semantic_mapping(column_map: Mapping[str, object]) -> dict[str, str]:
    schema = column_map.get("__schema__", {}) if isinstance(column_map, Mapping) else {}
    if not isinstance(schema, Mapping):
        return {}
    semantic = schema.get("semantic", {})
    return dict(semantic) if isinstance(semantic, Mapping) else {}
