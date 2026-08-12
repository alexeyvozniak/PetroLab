from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

import pandas as pd

COMMON_OXIDES = {
    "SiO2", "TiO2", "Al2O3", "Cr2O3", "Fe2O3", "FeO", "MnO", "MgO",
    "CaO", "Na2O", "K2O", "P2O5", "NiO", "BaO", "SrO", "ZnO", "V2O3",
    "F", "Cl", "H2O", "ZrO2", "HfO2", "Nb2O5", "Ta2O5", "La2O3", "Ce2O3", "Nd2O3", "Y2O3", "ThO2", "UO2", "V2O5", "SO3"
}

ALIASES = {
    "sio2": "SiO2", "si o2": "SiO2", "sio₂": "SiO2",
    "tio2": "TiO2", "tio₂": "TiO2",
    "al2o3": "Al2O3", "al₂o₃": "Al2O3",
    "cr2o3": "Cr2O3", "cr₂o₃": "Cr2O3",
    "fe2o3": "Fe2O3", "fe₂o₃": "Fe2O3",
    "feo": "FeO", "feot": "FeO", "feo*": "FeO",
    "mno": "MnO", "mgo": "MgO", "cao": "CaO",
    "na2o": "Na2O", "na₂o": "Na2O",
    "k2o": "K2O", "k₂o": "K2O",
    "p2o5": "P2O5", "p₂o₅": "P2O5",
    "nio": "NiO", "bao": "BaO", "sro": "SrO", "zno": "ZnO",
    "f": "F", "cl": "Cl", "h2o": "H2O", "h₂o": "H2O",
    "zro2": "ZrO2", "hfo2": "HfO2", "nb2o5": "Nb2O5", "ta2o5": "Ta2O5",
    "la2o3": "La2O3", "ce2o3": "Ce2O3", "nd2o3": "Nd2O3", "y2o3": "Y2O3",
    "tho2": "ThO2", "uo2": "UO2", "v2o5": "V2O5", "so3": "SO3",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_column_name(value: object) -> str:
    text = str(value).strip()
    compact = re.sub(r"\s+", " ", text).lower()
    return ALIASES.get(compact, text)


def normalize_columns_with_map(df: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict]]:
    out = df.copy()
    normalized = []
    mapping: dict[str, dict] = {}
    seen: dict[str, int] = {}
    for idx, original in enumerate(df.columns, start=1):
        base = normalize_column_name(original)
        seen[base] = seen.get(base, 0) + 1
        name = base if seen[base] == 1 else f"{base}__{seen[base]}"
        normalized.append(name)
        mapping[name] = {"original": str(original), "column_index": idx}
    out.columns = normalized
    return out, mapping


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    return normalize_columns_with_map(df)[0]


def numericize_oxide_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col in COMMON_OXIDES:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def oxide_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c in COMMON_OXIDES]


def add_qc_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = numericize_oxide_columns(df)
    oxides = [c for c in oxide_columns(out) if c not in {"F", "Cl", "H2O"}]
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
    bio = io.BytesIO(file_bytes)
    header = max(0, int(header_row) - 1)
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        df = pd.read_excel(bio, sheet_name=sheet_name or 0, header=header)
    elif suffix == ".csv":
        try:
            df = pd.read_csv(bio, sep=None, engine="python", header=header)
        except UnicodeDecodeError:
            bio.seek(0)
            df = pd.read_csv(bio, sep=None, engine="python", encoding="cp1251", header=header)
    else:
        raise ValueError("Поддерживаются файлы XLSX, XLSM, XLS и CSV")
    df, mapping = normalize_columns_with_map(df)
    df = add_qc_columns(df)
    source_rows = list(range(int(header_row) + 1, int(header_row) + 1 + len(df)))
    return df, mapping, source_rows


def read_tabular(file_bytes: bytes, filename: str, sheet_name: str | None = None, header_row: int = 1) -> pd.DataFrame:
    return read_tabular_with_map(file_bytes, filename, sheet_name, header_row)[0]


def read_tabular_path(
    path: str | Path,
    sheet_name: str | None = None,
    header_row: int = 1,
) -> tuple[pd.DataFrame, dict[str, dict], list[int]]:
    path = Path(path)
    return read_tabular_with_map(path.read_bytes(), path.name, sheet_name, header_row)


def numeric_candidates(df: pd.DataFrame, min_valid: int = 2, ratio: float = 0.65) -> list[str]:
    result = []
    for col in df.columns:
        if str(col).startswith("_"):
            continue
        series = df[col]
        nonnull = series.notna().sum()
        if nonnull < min_valid:
            continue
        converted = pd.to_numeric(series, errors="coerce")
        if converted.notna().sum() >= min_valid and converted.notna().sum() / max(nonnull, 1) >= ratio:
            result.append(col)
    return result
