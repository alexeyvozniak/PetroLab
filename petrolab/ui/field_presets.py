from __future__ import annotations

import re

import pandas as pd

from petrolab.column_schema import describe_header


FIELD_MODES = ("Основное", "Микрозонд", "Trace", "APFU", "QC", "Все", "Свои")
LEGACY_FIELD_MODES = {
    "Химия": "Микрозонд",
    "Расчёты": "APFU",
}

_MAJOR_PRIORITY = (
    "SiO2", "TiO2", "Al2O3", "Cr2O3", "FeOt", "FeO", "Fe2O3t", "Fe2O3",
    "MnO", "MgO", "CaO", "Na2O", "K2O", "P2O5", "NiO", "BaO", "SrO",
    "ZnO", "V2O3", "V2O5", "ZrO2", "HfO2", "Nb2O5", "Ta2O5", "SO3", "F", "Cl",
)
_TRACE_PRIORITY = (
    "Li", "Be", "B", "Sc", "V", "Cr", "Co", "Ni", "Cu", "Zn", "Ga", "Rb", "Sr",
    "Y", "Zr", "Nb", "Cs", "Ba", "La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb",
    "Dy", "Ho", "Er", "Tm", "Yb", "Lu", "Hf", "Ta", "Pb", "Th", "U",
)
_APFU_TOKENS = (
    "apfu", "cation", "катион", "site", "позици", "formula", "формул", "occup", "mg#", "fe#",
    "mg_no", "fe_no", "ratio", "отношен", "tetra", "octa", "iv", "vi",
)
_QC_TOKENS = (
    "qc", "quality", "качест", "decision", "решен", "status", "статус", "uncert", "неопредел",
    "sigma", "error", "ошиб", "detection", "detect", "dl", "lod", "loq", "total", "sum", "сумм",
    "valid", "валид", "warning", "предупр", "blank", "standard", "стандарт",
)
_UNIT_RE = re.compile(r"(?:ppm|ppb|ppt|[µμu]g\s*/\s*g|мкг\s*/\s*г|mg\s*/\s*kg|ng\s*/\s*g)", re.IGNORECASE)


def normalize_field_mode(mode: object) -> str:
    value = str(mode or "Основное")
    value = LEGACY_FIELD_MODES.get(value, value)
    return value if value in FIELD_MODES else "Основное"


def _public_columns(dataframe: pd.DataFrame) -> list[str]:
    return [str(column) for column in dataframe.columns if not str(column).startswith("_")]


def microprobe_columns(dataframe: pd.DataFrame) -> list[str]:
    available = _public_columns(dataframe)
    priority = [column for column in _MAJOR_PRIORITY if column in available]
    classified = []
    for column in available:
        if column in priority:
            continue
        descriptor = describe_header(column)
        if descriptor.quantity_kind == "oxide" or descriptor.canonical_unit == "wt%":
            classified.append(column)
    return list(dict.fromkeys([*priority, *classified]))


def _trace_rank(column: str) -> tuple[int, int, str]:
    descriptor = describe_header(column)
    canonical = descriptor.canonical_name.split(" ", 1)[0]
    try:
        rank = _TRACE_PRIORITY.index(canonical)
    except ValueError:
        rank = len(_TRACE_PRIORITY)
    explicit_unit = 0 if descriptor.quantity_kind in {"trace_element", "element_concentration"} else 1
    return explicit_unit, rank, column.casefold()


def trace_columns(dataframe: pd.DataFrame) -> list[str]:
    result: list[str] = []
    for column in _public_columns(dataframe):
        descriptor = describe_header(column)
        if descriptor.quantity_kind in {"trace_element", "element_concentration"}:
            result.append(column)
            continue
        # Bare element headers are still useful in a Trace view. They remain
        # unit-ambiguous in storage; this preset never converts or merges them.
        if descriptor.quantity_kind == "element_unknown_unit" and pd.api.types.is_numeric_dtype(dataframe[column]):
            result.append(column)
            continue
        if _UNIT_RE.search(column) and pd.api.types.is_numeric_dtype(dataframe[column]):
            result.append(column)
    return sorted(dict.fromkeys(result), key=_trace_rank)


def apfu_columns(dataframe: pd.DataFrame) -> list[str]:
    result: list[str] = []
    for column in _public_columns(dataframe):
        token = column.casefold().replace("₂", "2").replace("₃", "3")
        if any(part in token for part in _APFU_TOKENS):
            result.append(column)
            continue
        # Common structural-formula output names such as Si_T, Al_IV, Fe2+_M1.
        if re.search(r"(?:^|[_\s])(t|m[1-4]|a|b|iv|vi)(?:$|[_\s])", token) and pd.api.types.is_numeric_dtype(dataframe[column]):
            result.append(column)
    return result


def qc_columns(dataframe: pd.DataFrame) -> list[str]:
    result: list[str] = []
    for column in _public_columns(dataframe):
        token = column.casefold()
        if any(part in token for part in _QC_TOKENS):
            result.append(column)
    return result


def columns_for_mode(
    dataframe: pd.DataFrame,
    mode: object,
    *,
    identity_columns: tuple[str, ...] | list[str] = (),
) -> list[str]:
    normalized = normalize_field_mode(mode)
    identity = [column for column in identity_columns if column in dataframe.columns]
    if normalized == "Микрозонд":
        body = microprobe_columns(dataframe)
    elif normalized == "Trace":
        body = trace_columns(dataframe)
    elif normalized == "APFU":
        body = apfu_columns(dataframe)
    elif normalized == "QC":
        body = qc_columns(dataframe)
    elif normalized == "Все":
        body = _public_columns(dataframe)
    else:
        major = microprobe_columns(dataframe)[:8]
        trace = trace_columns(dataframe)[:4]
        body = [*major, *trace]
    return list(dict.fromkeys([*identity, *body]))
