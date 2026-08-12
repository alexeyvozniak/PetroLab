from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, Mapping

import pandas as pd

CANONICAL_ROLES = ("Sample", "Grain", "Point", "Generation")

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

# Group / Type / Zone / Population / Series are intentionally weak candidates for
# Generation: they are shown to the user but never renamed automatically.
WEAK_ROLE_CANDIDATES: dict[str, set[str]] = {
    "Generation": {"group", "type", "zone", "rimcore", "population", "series"},
}

# Total-iron reporting conventions stay distinct from measured valence-specific oxides.
OXIDE_ALIASES: dict[str, str] = {
    "sio2": "SiO2", "tio2": "TiO2", "al2o3": "Al2O3", "cr2o3": "Cr2O3",
    "fe2o3": "Fe2O3",
    "fe2o3t": "Fe2O3t", "fe2o3tot": "Fe2O3t", "fe2o3total": "Fe2O3t",
    "totalfeasfe2o3": "Fe2O3t", "fe2o3*": "Fe2O3t",
    "feo": "FeO", "feot": "FeOt", "feotot": "FeOt",
    "feototal": "FeOt", "totalfeasfeo": "FeOt", "feo*": "FeOt",
    "mno": "MnO", "mgo": "MgO", "cao": "CaO", "na2o": "Na2O", "k2o": "K2O",
    "p2o5": "P2O5", "nio": "NiO", "bao": "BaO", "sro": "SrO", "zno": "ZnO",
    "v2o3": "V2O3", "v2o5": "V2O5", "zro2": "ZrO2", "hfo2": "HfO2",
    "nb2o5": "Nb2O5", "ta2o5": "Ta2O5", "la2o3": "La2O3", "ce2o3": "Ce2O3",
    "nd2o3": "Nd2O3", "y2o3": "Y2O3", "tho2": "ThO2", "uo2": "UO2",
    "so3": "SO3", "h2o": "H2O", "f": "F", "cl": "Cl",
}

ELEMENT_SYMBOLS = {
    "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg", "Al",
    "Si", "P", "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr", "Mn", "Fe",
    "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br", "Kr", "Rb", "Sr", "Y",
    "Zr", "Nb", "Mo", "Ru", "Rh", "Pd", "Ag", "Cd", "In", "Sn", "Sb", "Te", "I",
    "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er",
    "Tm", "Yb", "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg", "Tl",
    "Pb", "Bi", "Th", "U",
}
_ELEMENT_BY_CASEFOLD = {symbol.casefold(): symbol for symbol in ELEMENT_SYMBOLS}

_UNIT_SUFFIX_RE = re.compile(
    r"[\s,;:_-]*(?:\(|\[)?\s*(?:wt\.?\s*%|wtpct|mass\s*%|мас\.?\s*%|weight\s*%)\s*(?:\)|\])?$",
    flags=re.IGNORECASE,
)
_CONCENTRATION_UNIT_RE = re.compile(
    r"(?:\(|\[)?\s*(ppm|ppb|ppt|[µμu]g\s*/\s*g|mg\s*/\s*kg|ng\s*/\s*g|pg\s*/\s*g|"
    r"[µμu]g\s+g(?:\^?[-−]?1|[⁻−-]¹)|mg\s+kg(?:\^?[-−]?1|[⁻−-]¹)|"
    r"ng\s+g(?:\^?[-−]?1|[⁻−-]¹)|pg\s+g(?:\^?[-−]?1|[⁻−-]¹)|"
    r"мкг\s*/\s*г|мг\s*/\s*кг|нг\s*/\s*г|пг\s*/\s*г|"
    r"мкг\s+г(?:\^?[-−]?1|[⁻−-]¹)|мг\s+кг(?:\^?[-−]?1|[⁻−-]¹)|"
    r"нг\s+г(?:\^?[-−]?1|[⁻−-]¹)|пг\s+г(?:\^?[-−]?1|[⁻−-]¹)|"
    r"wt\.?\s*%|mass\s*%|мас\.?\s*%)\s*(?:\)|\])?\s*$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class ColumnDescriptor:
    canonical_name: str
    quantity_kind: str
    source_unit: str
    canonical_unit: str
    to_canonical_factor: float
    to_source_factor: float
    warning: str = ""


@dataclass(frozen=True)
class SheetSchema:
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


def describe_header(value: object) -> ColumnDescriptor:
    """Classify one header and define reversible normalization when it is safe."""
    original = _nfkc(value)
    token = _token(original)
    if token in OXIDE_ALIASES:
        canonical = OXIDE_ALIASES[token]
        warnings = {
            "FeOt": "total Fe as FeO; not a measured FeO/Fe2+ value",
            "Fe2O3t": "total Fe as Fe2O3; not a measured Fe2O3/Fe3+ value",
        }
        return ColumnDescriptor(
            canonical, "oxide", "wt%", "wt%", 1.0, 1.0, warnings.get(canonical, "")
        )

    unit_match = _CONCENTRATION_UNIT_RE.search(original)
    if unit_match:
        source_unit, canonical_unit, factor = _normalize_concentration_unit(unit_match.group(1))
        element_text = original[:unit_match.start()].strip(" _-,:;()[]")
        element = _ELEMENT_BY_CASEFOLD.get(_nfkc(element_text).casefold())
        if element:
            canonical = f"{element} [{canonical_unit}]"
            return ColumnDescriptor(
                canonical_name=canonical,
                quantity_kind="trace_element" if canonical_unit == "µg/g" else "element_concentration",
                source_unit=source_unit,
                canonical_unit=canonical_unit,
                to_canonical_factor=factor,
                to_source_factor=1.0 / factor,
            )

    bare_element = _ELEMENT_BY_CASEFOLD.get(original.casefold())
    if bare_element:
        return ColumnDescriptor(
            bare_element,
            "element_unknown_unit",
            "",
            "",
            1.0,
            1.0,
            "Единица не указана в заголовке; автоматическое объединение с ppm/µg/g не выполняется.",
        )

    return ColumnDescriptor(original, "unknown", "", "", 1.0, 1.0)


def _normalize_concentration_unit(raw: str) -> tuple[str, str, float]:
    unit = _nfkc(raw).lower().replace("μ", "µ").replace("u", "µ")
    unit = unit.replace("−", "-").replace("⁻", "-").replace("¹", "1").replace("^", "")
    unit = re.sub(r"\s+", "", unit)
    if unit in {"ppm", "µg/g", "мкг/г", "mg/kg", "мг/кг", "µgg-1", "мкгг-1", "mgkg-1", "мгкг-1"}:
        return raw, "µg/g", 1.0
    if unit in {"ppb", "ng/g", "нг/г", "ngg-1", "нгг-1"}:
        return raw, "µg/g", 1e-3
    if unit in {"ppt", "pg/g", "пг/г", "pgg-1", "пгг-1"}:
        return raw, "µg/g", 1e-6
    if unit in {"wt%", "wt.%", "mass%", "мас.%", "мас%"}:
        return raw, "wt%", 1.0
    raise ValueError(f"Неподдерживаемая единица концентрации: {raw}")


def canonicalize_header(value: object) -> str:
    return describe_header(value).canonical_name


def infer_semantic_mapping(columns: Iterable[object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for column in columns:
        token = _token(column)
        for role, aliases in _SEMANTIC_TOKENS.items():
            if token in aliases and role not in result:
                result[role] = str(column)
                break
    return result


def resolve_semantic_mapping(
    columns: Iterable[object],
    stored_map: Mapping[str, str] | None,
) -> dict[str, str]:
    """Reuse confirmed roles, but recover safely from harmless header renames."""
    names = {str(column) for column in columns}
    inferred = infer_semantic_mapping(names)
    resolved: dict[str, str] = {}
    for role in CANONICAL_ROLES:
        previous = str((stored_map or {}).get(role, ""))
        if previous and previous in names:
            resolved[role] = previous
        elif role in names:
            resolved[role] = role
        elif role in inferred:
            resolved[role] = inferred[role]
    return resolved


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
    clean = validate_semantic_mapping(dataframe.columns, semantic_map)
    if not clean:
        mapped = dict(column_map)
        mapped.setdefault("__schema__", {})["semantic"] = {}
        return dataframe.copy(), mapped, {}

    rename_map = {source: role for role, source in clean.items() if source != role}
    out = dataframe.rename(columns=rename_map).copy()
    mapped = dict(column_map)
    for source, role in rename_map.items():
        info = dict(mapped.pop(source))
        info["normalized_from"] = source
        mapped[role] = info
    mapped.setdefault("__schema__", {})["semantic"] = clean
    return out, mapped, clean


def stored_semantic_mapping(column_map: Mapping[str, object]) -> dict[str, str]:
    schema = column_map.get("__schema__", {}) if isinstance(column_map, Mapping) else {}
    if not isinstance(schema, Mapping):
        return {}
    semantic = schema.get("semantic", {})
    return dict(semantic) if isinstance(semantic, Mapping) else {}
