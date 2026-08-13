from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

import pandas as pd

from petrolab.column_schema import ColumnDescriptor, describe_header

COMMON_OXIDES = {
    "SiO2", "TiO2", "Al2O3", "Cr2O3", "Fe2O3", "Fe2O3t", "FeO", "FeOt", "MnO", "MgO",
    "CaO", "Na2O", "K2O", "P2O5", "NiO", "BaO", "SrO", "ZnO", "V2O3",
    "F", "Cl", "H2O", "ZrO2", "HfO2", "Nb2O5", "Ta2O5", "La2O3", "Ce2O3",
    "Nd2O3", "Y2O3", "ThO2", "UO2", "V2O5", "SO3",
}

_PANDAS_DUPLICATE_RE = re.compile(r"^(?P<base>.+)\.(?P<index>[1-9]\d*)$")
_CENSORED_VALUE_RE = re.compile(
    r"^\s*(?P<operator><=|>=|<|>|≤|≥)\s*"
    r"(?P<value>[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*$"
)
_SCIENTIFIC_KINDS = {"oxide", "trace_element", "element_concentration"}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_column_name(value: object) -> str:
    return _import_descriptor(value)[0].canonical_name


def _import_descriptor(value: object) -> tuple[ColumnDescriptor, str]:
    """Recover known scientific headers that pandas mangled as duplicate `.1`, `.2`, ... names."""
    descriptor = describe_header(value)
    if descriptor.quantity_kind != "unknown":
        return descriptor, ""

    text = str(value).strip()
    match = _PANDAS_DUPLICATE_RE.match(text)
    if not match:
        return descriptor, ""
    base_descriptor = describe_header(match.group("base"))
    if base_descriptor.quantity_kind not in _SCIENTIFIC_KINDS:
        return descriptor, ""
    return (
        base_descriptor,
        "Повторяющийся научный заголовок был переименован pandas; проверьте конфликт исходных колонок.",
    )


def _scaled_scientific_value(value: object, factor: float) -> object:
    """Scale numeric chemistry while preserving explicit detection-limit qualifiers."""
    if pd.isna(value):
        return pd.NA
    if isinstance(value, str):
        text = value.strip()
        match = _CENSORED_VALUE_RE.match(text)
        if match:
            scaled = float(match.group("value")) * float(factor)
            return f"{match.group('operator')}{scaled:.12g}"
        try:
            return float(text) * float(factor)
        except ValueError:
            return value
    try:
        return float(value) * float(factor)
    except (TypeError, ValueError):
        return value


def _normalize_scientific_series(series: pd.Series, factor: float) -> pd.Series:
    return series.map(lambda value: _scaled_scientific_value(value, factor))


def normalize_columns_with_map(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict]]:
    """Normalize scientific headers, units, and retain reversible Excel provenance."""
    out = df.copy()
    normalized: list[str] = []
    descriptors: list[tuple[str, ColumnDescriptor]] = []
    mapping: dict[str, dict] = {}
    seen: dict[str, int] = {}

    for column_index, original in enumerate(df.columns, start=1):
        descriptor, import_warning = _import_descriptor(original)
        base = descriptor.canonical_name
        seen[base] = seen.get(base, 0) + 1
        name = base if seen[base] == 1 else f"{base}__{seen[base]}"
        normalized.append(name)
        descriptors.append((name, descriptor))
        warning = "; ".join(
            item for item in [descriptor.warning, import_warning] if item
        )
        mapping[name] = {
            "original": str(original),
            "column_index": column_index,
            "quantity_kind": descriptor.quantity_kind,
            "source_unit": descriptor.source_unit,
            "canonical_unit": descriptor.canonical_unit,
            "to_canonical_factor": descriptor.to_canonical_factor,
            "to_source_factor": descriptor.to_source_factor,
            "warning": warning,
        }

    out.columns = normalized
    for name, descriptor in descriptors:
        if descriptor.quantity_kind in _SCIENTIFIC_KINDS:
            out[name] = _normalize_scientific_series(out[name], descriptor.to_canonical_factor)

    return out, mapping


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    return normalize_columns_with_map(df)[0]


def numericize_scientific_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for column in out.columns:
        name = str(column)
        if name in COMMON_OXIDES or name.endswith("[µg/g]") or name.endswith("[wt%]"):
            out[column] = pd.to_numeric(out[column], errors="coerce")
    return out


def numericize_oxide_columns(df: pd.DataFrame) -> pd.DataFrame:
    return numericize_scientific_columns(df)


def oxide_columns(df: pd.DataFrame) -> list[str]:
    return [column for column in df.columns if column in COMMON_OXIDES]


def trace_element_columns(df: pd.DataFrame) -> list[str]:
    return [column for column in df.columns if str(column).endswith("[µg/g]")]


def _duplicate_oxide_inputs(columns: pd.Index) -> list[str]:
    conflicts: list[str] = []
    for column in columns:
        name = str(column)
        if "__" not in name:
            continue
        base, suffix = name.rsplit("__", 1)
        if suffix.isdigit() and base in COMMON_OXIDES:
            conflicts.append(name)
    return sorted(conflicts)


def _numeric_optional(df: pd.DataFrame, column: str) -> pd.Series:
    if column not in df.columns:
        return pd.Series(float("nan"), index=df.index, dtype=float)
    return pd.to_numeric(df[column], errors="coerce")


def add_qc_columns(df: pd.DataFrame) -> pd.DataFrame:
    # QC is computed from a numeric view, but the returned dataframe preserves source
    # semantics such as '<0.01' rather than destructively replacing them with NaN.
    out = df.copy()
    numeric = numericize_scientific_columns(df)
    duplicate_oxides = _duplicate_oxide_inputs(out.columns)
    if duplicate_oxides:
        out["QC химии"] = (
            "Конфликтующие химические колонки: " + ", ".join(duplicate_oxides)
        )

    non_fe_oxides = [
        column for column in oxide_columns(numeric)
        if column not in {"F", "Cl", "H2O", "FeO", "FeOt", "Fe2O3", "Fe2O3t"}
    ]
    base_sum = (
        numeric[non_fe_oxides].sum(axis=1, min_count=1)
        if non_fe_oxides
        else pd.Series(float("nan"), index=out.index, dtype=float)
    )

    feo = _numeric_optional(numeric, "FeO")
    fe2o3 = _numeric_optional(numeric, "Fe2O3")
    feot = _numeric_optional(numeric, "FeOt")
    fe2o3t = _numeric_optional(numeric, "Fe2O3t")

    total_overlap = feot.notna() & fe2o3t.notna()
    total_any = feot.notna() | fe2o3t.notna()
    split_any = feo.notna() | fe2o3.notna()
    total_split_overlap = total_any & split_any
    iron_conflict = total_overlap | total_split_overlap

    if iron_conflict.any():
        out["QC железа"] = "Проверьте: total Fe пересекается с другой формой представления Fe"

    # For oxide totals use whichever reporting basis was actually supplied row by row.
    # Split FeO + Fe2O3 is summed only when no total-Fe column is present in that row.
    total_reported = feot.combine_first(fe2o3t)
    split_reported = pd.concat([feo, fe2o3], axis=1).sum(axis=1, min_count=1)
    iron_contribution = total_reported.combine_first(split_reported)

    if base_sum.notna().any() or iron_contribution.notna().any():
        out["Σ оксидов"] = pd.concat([base_sum, iron_contribution], axis=1).sum(axis=1, min_count=1)
        invalid_sum = pd.Series(bool(duplicate_oxides), index=out.index) | iron_conflict
        normal_labels = pd.cut(
            out["Σ оксидов"],
            bins=[float("-inf"), 97.0, 103.0, float("inf")],
            labels=["низкая", "норма", "высокая"],
            right=True,
        ).astype("string")
        out["QC суммы"] = normal_labels
        out.loc[invalid_sum, "QC суммы"] = "конфликт колонок/железа"
    return out


def list_excel_sheets(file_bytes: bytes) -> list[str]:
    with pd.ExcelFile(io.BytesIO(file_bytes)) as book:
        return list(book.sheet_names)


def list_excel_sheets_path(path: str | Path) -> list[str]:
    with pd.ExcelFile(path) as book:
        return list(book.sheet_names)


def _drop_fully_empty_rows(df: pd.DataFrame, header_row: int) -> tuple[pd.DataFrame, list[int]]:
    """Drop separator rows while retaining their real Excel row positions for round trips."""
    if df.empty:
        return df.reset_index(drop=True), []
    comparable = df.replace(r"^\s*$", pd.NA, regex=True)
    keep_mask = ~comparable.isna().all(axis=1)
    source_rows = [
        int(header_row) + 1 + position
        for position, keep in enumerate(keep_mask.tolist())
        if keep
    ]
    return df.loc[keep_mask].reset_index(drop=True), source_rows


def read_tabular_with_map(
    file_bytes: bytes,
    filename: str,
    sheet_name: str | None = None,
    header_row: int = 1,
) -> tuple[pd.DataFrame, dict[str, dict], list[int]]:
    suffix = Path(filename).suffix.lower()
    source = io.BytesIO(file_bytes)
    header = max(0, int(header_row) - 1)
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        df = pd.read_excel(source, sheet_name=sheet_name or 0, header=header)
    elif suffix == ".csv":
        try:
            df = pd.read_csv(source, sep=None, engine="python", header=header)
        except UnicodeDecodeError:
            source.seek(0)
            df = pd.read_csv(source, sep=None, engine="python", encoding="cp1251", header=header)
    else:
        raise ValueError("Поддерживаются файлы XLSX, XLSM, XLS и CSV")

    df, source_rows = _drop_fully_empty_rows(df, int(header_row))
    df, mapping = normalize_columns_with_map(df)
    df = add_qc_columns(df)
    return df, mapping, source_rows


def read_tabular(
    file_bytes: bytes,
    filename: str,
    sheet_name: str | None = None,
    header_row: int = 1,
) -> pd.DataFrame:
    return read_tabular_with_map(file_bytes, filename, sheet_name, header_row)[0]


def read_tabular_path(
    path: str | Path,
    sheet_name: str | None = None,
    header_row: int = 1,
) -> tuple[pd.DataFrame, dict[str, dict], list[int]]:
    source_path = Path(path)
    return read_tabular_with_map(source_path.read_bytes(), source_path.name, sheet_name, header_row)


def numeric_candidates(df: pd.DataFrame, min_valid: int = 2, ratio: float = 0.65) -> list[str]:
    result: list[str] = []
    for column in df.columns:
        if str(column).startswith("_"):
            continue
        series = df[column]
        nonnull = series.notna().sum()
        if nonnull < min_valid:
            continue
        converted = pd.to_numeric(series, errors="coerce")
        if converted.notna().sum() >= min_valid and converted.notna().sum() / max(nonnull, 1) >= ratio:
            result.append(column)
    return result
