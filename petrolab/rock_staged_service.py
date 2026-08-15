from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from petrolab.column_schema import describe_header
from petrolab.repositories.rock_repository import (
    create_rock,
    get_composition,
    list_rocks,
    replace_composition,
    rock_connection,
)
from petrolab.rock_determinations import create_rock_determination, ensure_rock_determination_schema
from petrolab.row_provenance import canonical_sample_id, canonical_study_id
from petrolab.sample_registry import link_rock_record_to_sample, list_samples


CANONICAL_ROCK_FIELDS = {
    "Sample", "Lithology", "Source", "Method", "Laboratory", "Locality", "Massif",
    "Age", "Age uncertainty", "Age method",
}


@dataclass(frozen=True)
class RockStagedImportResult:
    rock_ids: tuple[int, ...]
    determination_ids: tuple[int, ...]
    created_rocks: int
    reused_rocks: int
    source_links: int
    custom_attributes: int
    warnings: tuple[str, ...]


def ensure_rock_staging_schema() -> None:
    ensure_rock_determination_schema()
    with rock_connection() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS rock_determination_attributes (
                determination_id INTEGER NOT NULL,
                field_name TEXT NOT NULL,
                field_value TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'staging',
                PRIMARY KEY(determination_id, field_name),
                FOREIGN KEY(determination_id) REFERENCES rock_determinations(id) ON DELETE CASCADE
            )
            """
        )
        con.commit()


def _text(value: object) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _float(value: object) -> float | None:
    text = _text(value)
    if not text:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _sample_name_by_id(project_id: int) -> dict[int, str]:
    return {int(item["id"]): str(item["name"]) for item in list_samples(int(project_id))}


def _rocks_by_sample_id(project_id: int) -> dict[int, dict]:
    result: dict[int, dict] = {}
    for rock in list_rocks(int(project_id)):
        sample_id = rock.get("sample_id")
        if sample_id is not None:
            result[int(sample_id)] = rock
    return result


def _metadata_from_row(row: pd.Series) -> dict:
    return {
        "lithology": _text(row.get("Lithology")),
        "massif": _text(row.get("Massif")),
        "locality": _text(row.get("Locality")),
        "age_ma": _float(row.get("Age")),
        "age_uncertainty_ma": _float(row.get("Age uncertainty")),
        "age_method": _text(row.get("Age method")),
        "chemistry_method": _text(row.get("Method")),
        "laboratory": _text(row.get("Laboratory")),
    }


def _custom_attributes(row: pd.Series) -> dict[str, str]:
    attributes: dict[str, str] = {}
    for column, value in row.items():
        name = str(column)
        if name in CANONICAL_ROCK_FIELDS or name.startswith("_"):
            continue
        descriptor = describe_header(name)
        if descriptor.quantity_kind in {"oxide", "trace_element", "element_concentration", "element_unknown_unit"}:
            continue
        text = _text(value)
        if text:
            attributes[name] = text
    return attributes


def _save_attributes(determination_id: int, attributes: dict[str, str]) -> int:
    if not attributes:
        return 0
    ensure_rock_staging_schema()
    with rock_connection() as con:
        for key, value in attributes.items():
            con.execute(
                """
                INSERT INTO rock_determination_attributes(determination_id, field_name, field_value, source)
                VALUES (?, ?, ?, 'staging')
                ON CONFLICT(determination_id, field_name) DO UPDATE SET
                    field_value=excluded.field_value,
                    source=excluded.source
                """,
                (int(determination_id), str(key), str(value)),
            )
        con.commit()
    return len(attributes)


def import_staged_rocks(
    dataframe: pd.DataFrame,
    *,
    project_id: int,
    source_file: str = "",
    source_sheet: str = "",
    confirmed_samples: dict[str, int] | None = None,
    confirmed_sources: dict[str, int] | None = None,
) -> RockStagedImportResult:
    """Import one staged whole-rock table without overwriting repeated determinations.

    Every row becomes a determination. Rows confirmed as the same physical Sample
    share one canonical rock object; repeated chemistry is preserved as a separate
    determination instead of replacing the earlier analysis.
    """
    ensure_rock_staging_schema()
    if "Sample" not in dataframe.columns:
        raise ValueError("Для импорта пород нужно назначить поле Sample")

    sample_confirm = {str(key): int(value) for key, value in (confirmed_samples or {}).items()}
    source_confirm = {str(key): int(value) for key, value in (confirmed_sources or {}).items()}
    excluded = {column for column in dataframe.columns if str(column) in CANONICAL_ROCK_FIELDS}

    # Preflight chemistry before creating any new physical objects.
    prepared: list[dict] = []
    warnings: list[str] = []
    from petrolab.services.rock_service import canonicalize_rock_row
    for position, (_, row) in enumerate(dataframe.iterrows(), start=1):
        sample_label = _text(row.get("Sample"))
        if not sample_label:
            continue
        composition, units, row_warnings = canonicalize_rock_row(row, excluded_columns=excluded)
        if not composition:
            warnings.append(f"{sample_label}: не распознано химических компонентов")
        warnings.extend(f"{sample_label}: {message}" for message in row_warnings)
        prepared.append({
            "row": row,
            "position": position,
            "sample_label": sample_label,
            "composition": composition,
            "units": units,
            "metadata": _metadata_from_row(row),
            "attributes": _custom_attributes(row),
        })
    if not prepared:
        raise ValueError("В staging-таблице не найдено строк с Sample")

    rock_ids: list[int] = []
    determination_ids: list[int] = []
    created = reused = linked_sources = attribute_count = 0
    rocks_by_sample = _rocks_by_sample_id(int(project_id))

    for item in prepared:
        label = item["sample_label"]
        sample_id = canonical_sample_id(
            int(project_id),
            label,
            confirmed_existing_id=sample_confirm.get(label),
        )
        if sample_id is None:
            continue
        canonical_names = _sample_name_by_id(int(project_id))
        canonical_name = canonical_names.get(int(sample_id), label)
        rock = rocks_by_sample.get(int(sample_id))
        if rock is None:
            rock_id = create_rock(int(project_id), canonical_name, **item["metadata"])
            link_rock_record_to_sample(int(rock_id), int(sample_id))
            rock = {"id": int(rock_id), "sample_id": int(sample_id), "name": canonical_name}
            rocks_by_sample[int(sample_id)] = rock
            created += 1
        else:
            rock_id = int(rock["id"])
            reused += 1

        source_label = _text(item["row"].get("Source"))
        study_id = None
        if source_label:
            study_id = canonical_study_id(
                int(project_id),
                source_label,
                confirmed_existing_id=source_confirm.get(source_label),
            )
            linked_sources += 1 if study_id is not None else 0
        method = _text(item["row"].get("Method"))
        laboratory = _text(item["row"].get("Laboratory"))
        determination_id = create_rock_determination(
            int(rock_id),
            item["composition"],
            units=item["units"],
            study_id=study_id,
            label=f"{canonical_name} · determination {item['position']}",
            source_label=source_label,
            method=method,
            laboratory=laboratory,
            source_file=source_file,
            source_sheet=source_sheet,
            source_row=int(item["position"]),
        )
        attribute_count += _save_attributes(int(determination_id), item["attributes"])

        # Preserve current plots and legacy views: only the first composition becomes
        # the default rock composition. Later determinations remain separate until the
        # user explicitly marks another one preferred.
        if get_composition(int(rock_id)).empty and item["composition"]:
            replace_composition(
                int(rock_id), item["composition"], units=item["units"],
                method=method, source=source_label or source_file,
            )
        rock_ids.append(int(rock_id))
        determination_ids.append(int(determination_id))

    return RockStagedImportResult(
        tuple(dict.fromkeys(rock_ids)), tuple(determination_ids), created, reused,
        linked_sources, attribute_count, tuple(warnings),
    )
