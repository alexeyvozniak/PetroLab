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
    r"(?P<value>[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?)\s*$"
)
_SCIENTIFIC_KINDS = {"oxide", "trace_element", "element_concentration"}
_AW_O = 15.999
_AW_F = 18.998403163
_AW_CL = 35.45


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
            scaled = float(match.group("value").replace(",", ".")) * float(factor)
            return f"{match.group('operator')}{scaled:.12g}"
        try:
            return float(text.replace(",", ".")) * float(factor)
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
        warning = "; ".join(item for item in [descriptor.warning, import_warning] if item)
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
    """Add transparent chemistry QC while preserving source values and qualifiers."""
    out = df.copy()
    numeric = numericize_scientific_columns(df)
    duplicate_oxides = _duplicate_oxide_inputs(out.columns)
    if duplicate_oxides:
        out["QC химии"] = "Конфликтующие химические колонки: " + ", ".join(duplicate_oxides)

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
    iron_conflict = total_overlap | (total_any & split_any)
    if iron_conflict.any():
        out["QC железа"] = "Проверьте: total Fe пересекается с другой формой представления Fe"

    total_reported = feot.combine_first(fe2o3t)
    split_reported = pd.concat([feo, fe2o3], axis=1).sum(axis=1, min_count=1)
    iron_contribution = total_reported.combine_first(split_reported)

    f = _numeric_optional(numeric, "F")
    cl = _numeric_optional(numeric, "Cl")
    halogens = pd.concat([f, cl], axis=1).sum(axis=1, min_count=1)
    raw_total = pd.concat([base_sum, iron_contribution, halogens], axis=1).sum(axis=1, min_count=1)
    oxygen_correction = f.fillna(0.0) * _AW_O / (2.0 * _AW_F)
    oxygen_correction += cl.fillna(0.0) * _AW_O / (2.0 * _AW_CL)
    corrected_total = raw_total - oxygen_correction

    if raw_total.notna().any():
        out["Σ компонентов raw"] = raw_total
        out["Поправка O=F,Cl"] = oxygen_correction
        out["Σ corrected"] = corrected_total
        # Backwards-compatible alias used by older views and exports.
        out["Σ оксидов"] = corrected_total
        invalid_sum = pd.Series(bool(duplicate_oxides), index=out.index) | iron_conflict
        normal_labels = pd.cut(
            corrected_total,
            bins=[float("-inf"), 97.0, 103.0, float("inf")],
            labels=["низкая", "норма", "высокая"],
            right=True,
        ).astype("string")
        out["QC суммы"] = normal_labels
        out.loc[invalid_sum, "QC суммы"] = "конфликт колонок/железа"
    _add_quality_status(out)
    return out


def _add_quality_status(df: pd.DataFrame) -> None:
    """Attach a conservative QC signal without deleting or silently excluding data.

    The automatic level is evidence, not a verdict about a mineral: altered phases
    and partial EDS quantifications can legitimately have low totals.  A researcher
    may later set ``QC решение`` to include or exclude a point for a particular use.
    """
    levels: list[str] = []
    reasons: list[str] = []
    totals = pd.to_numeric(df.get("Total", df.get("Σ corrected")), errors="coerce")
    for index in df.index:
        row_reasons: list[str] = []
        level = "ОК"
        total = totals.loc[index] if index in totals.index else float("nan")
        if pd.notna(total) and (float(total) < 60.0 or float(total) > 105.0):
            level = "Исключить по умолчанию"
            row_reasons.append(f"сумма {float(total):.2f}")
        elif pd.notna(total) and (float(total) < 85.0 or float(total) > 103.0):
            level = "Требует проверки"
            row_reasons.append(f"сумма {float(total):.2f}")
        iron = str(df.at[index, "QC железа"]) if "QC железа" in df.columns and pd.notna(df.at[index, "QC железа"]) else ""
        chemistry = str(df.at[index, "QC химии"]) if "QC химии" in df.columns and pd.notna(df.at[index, "QC химии"]) else ""
        if iron or chemistry:
            level = "Исключить по умолчанию"
            row_reasons.extend(part for part in (iron, chemistry) if part)
        levels.append(level)
        reasons.append("; ".join(row_reasons))
    df["QC уровень"] = levels
    df["QC причины"] = reasons
    if "QC решение" not in df.columns:
        df["QC решение"] = "Авто"


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


def _column_by_header(columns: pd.Index, *candidates: str) -> str | None:
    """Find a report column without depending on the laboratory's capitalization."""
    lookup = {str(column).strip().casefold(): str(column) for column in columns}
    for candidate in candidates:
        found = lookup.get(candidate.casefold())
        if found is not None:
            return found
    return None


def _comment_sample_and_point(value: object) -> tuple[object, object]:
    """Split the conventional ``sample point`` WDS comment, keeping text point IDs."""
    if pd.isna(value):
        return pd.NA, pd.NA
    text = str(value).strip()
    if not text:
        return pd.NA, pd.NA
    parts = text.rsplit(maxsplit=1)
    if len(parts) == 1:
        return parts[0], pd.NA
    return parts[0], parts[1]


def _adapt_wds_report_rows(
    df: pd.DataFrame,
    mapping: dict[str, dict],
    source_rows: list[int],
) -> tuple[pd.DataFrame, dict[str, dict], list[int]]:
    """Make a conventional EPMA/WDS protocol safe to import.

    Laboratories often repeat the header between sample blocks.  Such rows look
    non-empty to Excel but are not analyses.  A WDS report is recognized only
    when it has both ``No.`` and ``Comment`` plus several chemistry columns, so
    ordinary user tables keep their original behaviour.
    """
    number_column = _column_by_header(df.columns, "No.", "No", "Analysis No.")
    comment_column = _column_by_header(df.columns, "Comment", "Comments", "Комментарий")
    chemistry_columns = [
        name for name, info in mapping.items()
        if info.get("quantity_kind") in _SCIENTIFIC_KINDS and name in df.columns
    ]
    if number_column is None or comment_column is None or len(chemistry_columns) < 3:
        return df, mapping, source_rows

    analysis_number = pd.to_numeric(df[number_column], errors="coerce")
    chemistry_count = pd.DataFrame(
        {name: pd.to_numeric(df[name], errors="coerce").notna() for name in chemistry_columns}
    ).sum(axis=1)
    # Three measured components make the rule tolerant of partially reported
    # analyses, while headers and separators cannot pass it.
    keep = analysis_number.notna() & chemistry_count.ge(3)
    if not keep.any():
        return df, mapping, source_rows

    out = df.loc[keep].reset_index(drop=True).copy()
    retained_rows = [row for row, include in zip(source_rows, keep.tolist()) if include]

    # Preserve the untouched laboratory comment and add convenient suggested
    # identity columns. The user may still change these assignments in import UI.
    if "Sample" not in out.columns:
        pairs = out[comment_column].map(_comment_sample_and_point)
        out["Sample"] = pairs.map(lambda pair: pair[0])
        mapping["Sample"] = {
            "original": f"{mapping[comment_column]['original']} (автоматически: образец)",
            "column_index": None,
            "quantity_kind": "identifier",
            "source_unit": "",
            "canonical_unit": "",
            "to_canonical_factor": 1.0,
            "to_source_factor": 1.0,
            "warning": "Автоматически выделено из Comment; проверьте перед импортом.",
        }
    if "Point" not in out.columns:
        pairs = out[comment_column].map(_comment_sample_and_point)
        out["Point"] = pairs.map(lambda pair: pair[1])
        mapping["Point"] = {
            "original": f"{mapping[comment_column]['original']} (автоматически: точка)",
            "column_index": None,
            "quantity_kind": "identifier",
            "source_unit": "",
            "canonical_unit": "",
            "to_canonical_factor": 1.0,
            "to_source_factor": 1.0,
            "warning": "Автоматически выделено из Comment; текстовые номера точек сохранены.",
        }
    mapping[comment_column]["wds_protocol"] = True
    return out, mapping, retained_rows


def _attach_wds_detection_limits(
    mapping: dict[str, dict],
    file_bytes: bytes,
    sheet_name: str | None,
    header_row: int,
) -> None:
    """Read the ``D.L. 3σ`` row immediately above a recognized WDS header."""
    try:
        raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name or 0, header=None)
    except Exception:
        return
    header_index = int(header_row) - 1
    if header_index < 1 or header_index >= len(raw):
        return
    candidate_rows = range(max(0, header_index - 3), header_index)
    dl_row = next(
        (
            index for index in reversed(list(candidate_rows))
            if raw.iloc[index].astype("string").str.contains(
                r"(?:D\.?L\.?|LOD|LOQ)", case=False, regex=True, na=False
            ).any()
        ),
        None,
    )
    if dl_row is None:
        return
    for info in mapping.values():
        column_index = info.get("column_index")
        if not isinstance(column_index, int) or column_index < 1 or column_index > raw.shape[1]:
            continue
        if info.get("quantity_kind") not in _SCIENTIFIC_KINDS:
            continue
        value = pd.to_numeric(pd.Series([raw.iat[dl_row, column_index - 1]]), errors="coerce").iat[0]
        if pd.isna(value):
            continue
        factor = float(info.get("to_canonical_factor", 1.0) or 1.0)
        info["detection_limit_source"] = float(value)
        info["detection_limit"] = float(value) * factor
        info["detection_limit_unit"] = info.get("canonical_unit") or info.get("source_unit") or ""


def _adapt_wds_report(
    df: pd.DataFrame,
    mapping: dict[str, dict],
    source_rows: list[int],
    *,
    file_bytes: bytes,
    suffix: str,
    sheet_name: str | None,
    header_row: int,
) -> tuple[pd.DataFrame, dict[str, dict], list[int]]:
    out, out_mapping, out_rows = _adapt_wds_report_rows(df, mapping, source_rows)
    if suffix in {".xls", ".xlsx", ".xlsm"} and any(
        info.get("wds_protocol") for info in out_mapping.values()
    ):
        _attach_wds_detection_limits(out_mapping, file_bytes, sheet_name, header_row)
    return out, out_mapping, out_rows


def _eds_section_label(raw: pd.DataFrame, header_index: int) -> str:
    """Return the nearby human block title (e.g. ``Флогопиты и хлориты``)."""
    for index in range(header_index - 1, max(-1, header_index - 6), -1):
        values = [str(value).strip() for value in raw.iloc[index].tolist() if pd.notna(value)]
        values = [value for value in values if value]
        if not values:
            continue
        text = " · ".join(values)
        if "no. of data" not in text.casefold() and text.casefold() not in {"масс %", "mass %"}:
            return text
    return "EDS block"


def _eds_sample_map(file_bytes: bytes, raw: pd.DataFrame) -> dict[str, str]:
    """Recover thin-section/sample names from the map sheet without guessing aliases."""
    values = [str(value).strip() for value in raw.to_numpy().ravel() if pd.notna(value) and str(value).strip()]
    # The accompanying BSE map sheet normally contains the full thin-section IDs,
    # while the report table keeps only a short prefix such as ``23-Phl``.
    try:
        with pd.ExcelFile(io.BytesIO(file_bytes)) as book:
            for other_sheet in book.sheet_names:
                other = pd.read_excel(io.BytesIO(file_bytes), sheet_name=other_sheet, header=None)
                values.extend(str(value).strip() for value in other.to_numpy().ravel() if pd.notna(value) and str(value).strip())
    except Exception:
        pass
    text = " ".join(values)
    candidates = re.findall(r"\b\d+[A-Za-zА-Яа-яЁё]+(?:-\d+(?:/\d+)?)?\b", text)
    result: dict[str, str] = {}
    for candidate in candidates:
        prefix = re.match(r"\d+", candidate)
        if prefix:
            result.setdefault(prefix.group(0), candidate)
    return result


def _eds_comment_parts(value: object) -> tuple[object, object]:
    if pd.isna(value):
        return pd.NA, pd.NA
    text = str(value).strip()
    if not text:
        return pd.NA, pd.NA
    first = text.split()[0]
    prefix = first.split("-", 1)[0]
    label = first.split("-", 1)[1] if "-" in first else ""
    # A note such as "не гранат" takes precedence over a terse comment label.
    if "не гранат" in text.casefold():
        label = ""
    return prefix, label


def _eds_mineral_candidate(label: object) -> object:
    token = str(label or "").strip().casefold()
    mapping = {
        "phl": "phlogopite", "mica": "phlogopite", "chl": "chlorite",
        "cpx": "clinopyroxene", "prv": "perovskite", "pvr": "perovskite",
        "sp": "spinel", "ap": "apatite",
    }
    return mapping.get(token, pd.NA)


def _import_eds_multiblock_report(
    file_bytes: bytes,
    sheet_name: str | None,
) -> tuple[pd.DataFrame, dict[str, dict], list[int]] | None:
    """Read an EDS report with several independently headed chemistry blocks.

    These exports often put mica, pyroxene, perovskite and apatite tables on one
    sheet. Their oxide order changes from block to block, so treating the sheet as
    one dataframe would silently assign chemistry to the wrong components.
    """
    try:
        raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=sheet_name or 0, header=None)
    except Exception:
        return None
    headers = [
        index for index in range(len(raw))
        if str(raw.iat[index, 0]).strip().casefold() in {"no.", "no"}
        and raw.iloc[index].astype("string").str.contains("comment", case=False, na=False).any()
    ]
    if len(headers) < 2:
        return None

    sample_map = _eds_sample_map(file_bytes, raw)
    frames: list[pd.DataFrame] = []
    source_rows: list[int] = []
    combined_map: dict[str, dict] = {}
    for position, header_index in enumerate(headers):
        end = headers[position + 1] if position + 1 < len(headers) else len(raw)
        block = raw.iloc[header_index + 1:end].copy()
        block.columns = raw.iloc[header_index].tolist()
        block, block_rows = _drop_fully_empty_rows(block, header_index + 1)
        block, block_map = normalize_columns_with_map(block)
        number_column = _column_by_header(block.columns, "No.", "No")
        chemistry = [
            column for column, info in block_map.items()
            if info.get("quantity_kind") in _SCIENTIFIC_KINDS and column in block.columns
        ]
        if number_column is None or len(chemistry) < 3:
            continue
        numeric_number = pd.to_numeric(block[number_column], errors="coerce")
        chemistry_count = pd.DataFrame({
            column: pd.to_numeric(block[column], errors="coerce").notna()
            for column in chemistry
        }).sum(axis=1)
        keep = numeric_number.notna() & chemistry_count.ge(3)
        if not keep.any():
            continue
        block = block.loc[keep].reset_index(drop=True).copy()
        retained_rows = [row for row, include in zip(block_rows, keep.tolist()) if include]
        comment_column = _column_by_header(block.columns, "Comment", "Comments", "Комментарий")
        section = _eds_section_label(raw, header_index)
        block["Import section"] = section
        block["Import analysis No."] = numeric_number.loc[keep].reset_index(drop=True).astype("Int64")
        if comment_column:
            parts = block[comment_column].map(_eds_comment_parts)
            prefixes = parts.map(lambda part: part[0])
            labels = parts.map(lambda part: part[1])
            block["Sample"] = prefixes.map(lambda value: sample_map.get(str(value), value))
            block["Thin section"] = block["Sample"]
            block["Mineral candidate"] = labels.map(_eds_mineral_candidate)
            block["Import label"] = block[comment_column]
        else:
            block["Sample"] = pd.NA
            block["Thin section"] = pd.NA
            block["Mineral candidate"] = pd.NA
            block["Import label"] = pd.NA
        block["Point"] = block["Import analysis No."].astype("string")
        for name, original, kind, warning in (
            ("Import section", "Заголовок блока EDS", "identifier", "Автоматически выделенный блок отчёта EDS."),
            ("Import analysis No.", "No. (исходный номер EDS)", "identifier", "Сохраняется вместе с Point; номера могут повторяться между блоками."),
            ("Sample", "Comment/карта шлифа (автоматически)", "identifier", "Сопоставление со шлифом извлечено из книги; подтвердите перед импортом."),
            ("Thin section", "Comment/карта шлифа (автоматически)", "identifier", "Привязка к шлифу из карты EDS."),
            ("Mineral candidate", "Comment (кандидат минерала)", "identifier", "Это подсказка, не подтверждённая минералогическая классификация."),
            ("Import label", "Comment", "identifier", "Исходная метка EDS сохранена без изменения."),
            ("Point", "No. (автоматически)", "identifier", "Номер точки EDS; не является глобальным уникальным ID."),
        ):
            block_map[name] = {
                "original": original, "column_index": None, "quantity_kind": kind,
                "source_unit": "", "canonical_unit": "", "to_canonical_factor": 1.0,
                "to_source_factor": 1.0, "warning": warning,
            }
        frames.append(block)
        source_rows.extend(retained_rows)
        for name, info in block_map.items():
            combined_map.setdefault(name, info)

    if not frames:
        return None
    combined = pd.concat(frames, ignore_index=True, sort=False)
    combined_map["__schema__"] = {
        "adapter": "eds_multiblock",
        "sections": [str(frame["Import section"].iloc[0]) for frame in frames],
        "zero_policy": "Исходные нули сохранены как нули; не интерпретированы как <DL> автоматически.",
    }
    return combined, combined_map, source_rows


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
        eds = _import_eds_multiblock_report(file_bytes, sheet_name)
        if eds is not None:
            df, mapping, source_rows = eds
            return add_qc_columns(df), mapping, source_rows
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
    df, mapping, source_rows = _adapt_wds_report(
        df,
        mapping,
        source_rows,
        file_bytes=file_bytes,
        suffix=suffix,
        sheet_name=sheet_name,
        header_row=int(header_row),
    )
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
