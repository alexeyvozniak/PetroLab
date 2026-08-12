from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pandas as pd

from petrolab.column_schema import describe_header

COMMON_OXIDES = {
    "SiO2", "TiO2", "Al2O3", "Cr2O3", "Fe2O3", "FeO", "FeOt", "MnO", "MgO",
    "CaO", "Na2O", "K2O", "P2O5", "NiO", "BaO", "SrO", "ZnO", "V2O3",
    "F", "Cl", "H2O", "ZrO2", "HfO2", "Nb2O5", "Ta2O5", "La2O3", "Ce2O3",
    "Nd2O3", "Y2O3", "ThO2", "UO2", "V2O5", "SO3",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_column_name(value: object) -> str:
    return describe_header(value).canonical_name


def normalize_columns_with_map(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict]]:
    """Normalize scientific headers, units, and retain reversible Excel provenance."""
    out = df.copy()
    normalized: list[str] = []
    descriptors = []
    mapping: dict[str, dict] = {}
    seen: dict[str, int] = {}

    for column_index, original in enumerate(df.columns, start=1):
        descriptor = describe_header(original)
        base = descriptor.canonical_name
        seen[base] = seen.get(base, 0) + 1
        name = base if seen[base] == 1 else f"{base}__{seen[base]}"
        normalized.append(name)
        descriptors.append((name, descriptor))
        mapping[name] = {
            "original": str(original),
            "column_index": column_index,
            "quantity_kind": descriptor.quantity_kind,
            "source_unit": descriptor.source_unit,
            "canonical_unit": descriptor.canonical_unit,
            "to_canonical_factor": descriptor.to_canonical_factor,
            "to_source_factor": descriptor.to_source_factor,
            "warning": descriptor.warning,
        }

    out.columns = normalized
    for name, descriptor in descriptors:
        if descriptor.quantity_kind in {"oxide", "trace_element", "element_concentration"}:
            numeric = pd.to_numeric(out[name], errors="coerce")
            if descriptor.to_canonical_factor != 1.0:
                numeric = numeric * descriptor.to_canonical_factor
            out[name] = numeric

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


def add_qc_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = numericize_scientific_columns(df)
    oxides = [
        column for column in oxide_columns(out)
        if column not in {"F", "Cl", "H2O", "FeO", "FeOt", "Fe2O3"}
    ]

    # Iron requires special handling to avoid silently double-counting total Fe.
    if "FeOt" in out.columns:
        oxides.append("FeOt")
        if "FeO" in out.columns or "Fe2O3" in out.columns:
            out["QC железа"] = "Проверьте: FeOt присутствует вместе с раздельными формами Fe"
    else:
        if "FeO" in out.columns:
            oxides.append("FeO")
        if "Fe2O3" in out.columns:
            oxides.append("Fe2O3")

    if oxides:
        out["Σ оксидов"] = out[oxides].sum(axis=1, min_count=1)
        out["QC суммы"] = pd.cut(
            out["Σ оксидов"],
            bins=[float("-inf"), 97.0, 103.0, float("inf")],
            labels=["низкая", "норма", "высокая"],
            right=True,
        ).astype("string")
    return out


def list_excel_sheets(file_bytes: bytes) -> list[str]:
    with pd.ExcelFile(io.BytesIO(file_bytes)) as book:
        return list(book.sheet_names)


def list_excel_sheets_path(path: str | Path) -> list[str]:
    with pd.ExcelFile(path) as book:
        return list(book.sheet_names)


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

    df, mapping = normalize_columns_with_map(df)
    df = add_qc_columns(df)
    source_rows = list(range(int(header_row) + 1, int(header_row) + 1 + len(df)))
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
