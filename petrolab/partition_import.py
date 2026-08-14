"""Import partition-coefficient tables while preserving their scientific identity.

The GERM KdD export has plural field names (rock_types, minerals) and often
contains intervals instead of a single Kd. This importer deliberately keeps
these statements separate: it never turns an interval into a mean and it never
assigns an equilibrium interpretation automatically.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Any

import pandas as pd

from petrolab.partitioning import create_partition_model


_ALIASES = {
    "rock type": "rock_type",
    "rock types": "rock_type",
    "rock_type": "rock_type",
    "rock_types": "rock_type",
    "mineral": "mineral",
    "minerals": "mineral",
    "element": "element",
    "elem": "element",
    "value": "value",
    "kd": "value",
    "kd sigma": "sd",
    "kd_sigma": "sd",
    "sigma": "sd",
    "low": "low",
    "kd low": "low",
    "kd_low": "low",
    "high": "high",
    "kd high": "high",
    "kd_high": "high",
    "reference": "reference",
    "citation": "reference",
    "doi": "doi",
    "contribution": "contribution_id",
    "contribution id": "contribution_id",
    "contribution_id": "contribution_id",
    "kd type": "kind",
    "kd types": "kind",
    "kd_type": "kind",
    "kd_types": "kind",
    "type": "kind",
    "kd definition": "definition",
    "kd_definition": "definition",
}


def _number(value: object) -> float | None:
    number = pd.to_numeric(value, errors="coerce")
    return float(number) if pd.notna(number) else None


def _first_text(group: pd.DataFrame, column: str) -> str:
    if column not in group:
        return ""
    values = group[column].dropna().astype(str)
    return values.iloc[0].strip() if not values.empty else ""


def _source_label(group: pd.DataFrame) -> str:
    cited = _first_text(group, "reference")
    if cited:
        return cited
    contribution = _first_text(group, "contribution_id")
    return f"GERM contribution {contribution}" if contribution else "GERM KdD import"


def _element_record(row: pd.Series) -> dict[str, float]:
    """Keep the exact value and any reported uncertainty/range as distinct fields."""
    record: dict[str, float] = {}
    for column in ("value", "sd", "low", "high"):
        number = _number(row.get(column))
        if number is not None:
            record[column] = number
    return record


def import_partition_table(dataframe: pd.DataFrame) -> list[int]:
    """Import a generic or GERM KdD results table.

    Exact Kd values are retained as numeric model values. Intervals and
    uncertainty remain in source.element_metadata; interval-only rows are
    preserved there and are not silently converted into a point estimate.
    """
    renamed = {
        column: _ALIASES.get(str(column).strip().casefold(), str(column).strip().casefold())
        for column in dataframe.columns
    }
    df = dataframe.rename(columns=renamed).copy()
    required = {"rock_type", "mineral", "element"}
    if not required.issubset(df.columns):
        raise ValueError("Нужны колонки Rock Type(s), Mineral(s) и Element.")
    if not ({"value", "low", "high"} & set(df.columns)):
        raise ValueError("Нужна хотя бы одна колонка: Kd/Value, Kd Low или Kd High.")

    df = df.dropna(subset=["rock_type", "mineral", "element"])
    if df.empty:
        return []

    grouping = ["rock_type", "mineral"]
    for column in ("contribution_id", "reference", "definition", "kind"):
        if column in df.columns:
            grouping.append(column)

    created: list[int] = []
    for keys, group in df.groupby(grouping, dropna=False):
        key_map = dict(zip(grouping, keys if isinstance(keys, tuple) else (keys,)))
        rock = str(key_map["rock_type"]).strip()
        mineral = str(key_map["mineral"]).strip()
        reference = _source_label(group)
        values: dict[str, float] = {}
        metadata: dict[str, dict[str, float]] = {}

        for _, row in group.iterrows():
            element = str(row["element"]).strip()
            record = _element_record(row)
            if not element or not record:
                continue
            # One model has one unambiguous value per element. Do not overwrite
            # a previous report if an export unexpectedly repeats the element.
            if element in metadata:
                suffix = 2
                candidate = f"{element} ({suffix})"
                while candidate in metadata:
                    suffix += 1
                    candidate = f"{element} ({suffix})"
                element = candidate
            metadata[element] = record
            # Exact values remain numerics for simple calculation; a range-only
            # report remains a structured value instead of being discarded or
            # reduced to an arbitrary midpoint.
            values[element] = record["value"] if "value" in record else record

        if not values:
            continue

        doi = _first_text(group, "doi")
        source: dict[str, Any] = {
            "citation": reference,
            "doi": doi,
            "database": "GERM KdD" if "contribution_id" in df.columns else "tabular import",
            "contribution_id": _first_text(group, "contribution_id"),
            "element_metadata": metadata,
            "raw_basis": "element",
        }
        definition = _first_text(group, "definition")
        kind = _first_text(group, "kind")
        if definition:
            source["kd_definition"] = definition
        if kind:
            source["kd_types"] = kind

        model_name = f"{reference} — {mineral}/{rock}"
        created.append(
            create_partition_model(
                model_name,
                mineral,
                "silicate_melt",
                "fixed_table",
                values,
                source=source,
                applicability={
                    "rock": rock,
                    "definition": definition,
                    "kind": kind,
                    "import": "raw literature table; review before default use",
                },
            )
        )
    return created


def read_partition_upload(raw: bytes, filename: str) -> pd.DataFrame:
    """Read the user-facing CSV/TSV/XLSX variants of a partition table."""
    suffix = Path(filename).suffix.casefold()
    if suffix in {".xlsx", ".xls"}:
        sheets = pd.read_excel(BytesIO(raw), sheet_name=None)
        for _, candidate in sheets.items():
            names = {
                _ALIASES.get(str(column).strip().casefold(), str(column).strip().casefold())
                for column in candidate.columns
            }
            if {"rock_type", "mineral", "element"} <= names:
                return candidate
        raise ValueError("В Excel не найден лист с Rock Type(s), Mineral(s) и Element.")

    try:
        return pd.read_csv(BytesIO(raw), sep=None, engine="python")
    except UnicodeDecodeError:
        return pd.read_csv(BytesIO(raw), sep=None, engine="python", encoding="latin-1")
