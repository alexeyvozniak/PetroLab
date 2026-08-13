from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from petrolab.column_schema import describe_header
from petrolab.repositories.rock_repository import (
    apply_rock_import_batch,
    delete_rock,
    get_composition,
    list_mineral_links,
    list_rocks,
)
from petrolab.services.rock_image_service import list_rock_images


MAJOR_OXIDES = {
    "SiO2", "TiO2", "Al2O3", "Cr2O3", "Fe2O3", "Fe2O3t", "FeO", "FeOt",
    "MnO", "MgO", "CaO", "Na2O", "K2O", "P2O5", "NiO", "BaO", "SrO",
}
M_MGO = 40.304
M_FEO = 71.844
M_FE2O3 = 159.688
FE2O3_TO_FEO_EQUIVALENT = 2.0 * M_FEO / M_FE2O3


@dataclass(frozen=True)
class RockImportResult:
    created_ids: tuple[int, ...]
    updated_ids: tuple[int, ...]
    skipped_names: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class RhodesResult:
    rock_mg_number: float
    kd_lines: dict[float, float]


def canonicalize_rock_row(row: pd.Series, excluded_columns: set[str] | None = None) -> tuple[dict[str, float], dict[str, str], list[str]]:
    excluded_columns = excluded_columns or set()
    composition: dict[str, float] = {}
    units: dict[str, str] = {}
    source_columns: dict[str, str] = {}
    warnings: list[str] = []
    for column, raw_value in row.items():
        if str(column) in excluded_columns:
            continue
        descriptor = describe_header(column)
        if descriptor.quantity_kind not in {"oxide", "trace_element", "element_concentration", "element_unknown_unit"}:
            continue
        numeric = pd.to_numeric(pd.Series([raw_value]), errors="coerce").iloc[0]
        if pd.isna(numeric):
            continue
        canonical = descriptor.canonical_name
        if canonical in composition:
            raise ValueError(
                f"Колонки «{source_columns[canonical]}» и «{column}» обе обозначают {canonical}. "
                "Выберите один источник этого компонента до импорта."
            )
        composition[canonical] = float(numeric) * float(descriptor.to_canonical_factor)
        units[canonical] = descriptor.canonical_unit or descriptor.source_unit
        source_columns[canonical] = str(column)
        if descriptor.warning:
            warnings.append(f"{column}: {descriptor.warning}")
    return composition, units, warnings


def _clean_import_names(dataframe: pd.DataFrame, name_column: str) -> list[str]:
    names: list[str] = []
    for raw in dataframe[name_column].tolist():
        if raw is None:
            continue
        try:
            if pd.isna(raw):
                continue
        except (TypeError, ValueError):
            pass
        name = str(raw).strip()
        if name:
            names.append(name)
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(
            "В импортируемой таблице повторяются названия пород/образцов: " + ", ".join(duplicates[:20]) +
            ". Сделайте названия уникальными до импорта, чтобы строки нельзя было перепутать."
        )
    return names


def _existing_composition_with_units(rock_id: int) -> tuple[dict[str, float], dict[str, str]]:
    dataframe = get_composition(int(rock_id))
    if dataframe.empty:
        return {}, {}
    composition = {
        str(row["analyte"]): float(row["value"])
        for _, row in dataframe.iterrows()
        if pd.notna(row.get("value"))
    }
    units = {
        str(row["analyte"]): str(row.get("unit") or "")
        for _, row in dataframe.iterrows()
        if str(row.get("analyte") or "").strip()
    }
    return composition, units


def import_rocks_wide(
    dataframe: pd.DataFrame,
    *,
    project_id: int,
    name_column: str,
    metadata_columns: dict[str, str] | None = None,
    chemistry_method: str = "",
    laboratory: str = "",
    source: str = "",
    on_conflict: str = "update",
) -> RockImportResult:
    if name_column not in dataframe.columns:
        raise ValueError(f"Колонка названия породы «{name_column}» отсутствует.")
    if on_conflict not in {"update", "skip", "error"}:
        raise ValueError("Неизвестная политика совпадающих названий пород")

    names = _clean_import_names(dataframe, name_column)
    existing = {str(rock["name"]): rock for rock in list_rocks(project_id)}
    conflicts = sorted(name for name in names if name in existing)
    if conflicts and on_conflict == "error":
        raise ValueError(
            "Такие породы уже есть в проекте: " + ", ".join(conflicts[:20]) +
            ". Выберите «обновить» или «пропустить»."
        )

    metadata_columns = metadata_columns or {}
    warnings: list[str] = []
    excluded = {name_column, *metadata_columns.values()}
    prepared_rows: list[dict] = []

    # Prepare every row before opening the write transaction. A conversion/validation
    # failure therefore cannot leave a partially imported batch behind.
    for _, row in dataframe.iterrows():
        raw_name = row.get(name_column, "")
        try:
            if pd.isna(raw_name):
                continue
        except (TypeError, ValueError):
            pass
        name = str(raw_name).strip()
        if not name:
            continue
        metadata = {
            key: row.get(column, "")
            for key, column in metadata_columns.items()
            if column in dataframe.columns
        }
        metadata["chemistry_method"] = chemistry_method
        metadata["laboratory"] = laboratory
        composition, units, row_warnings = canonicalize_rock_row(row, excluded)
        warnings.extend(f"{name}: {message}" for message in row_warnings)

        # "Update" means update the fields supplied by this table, not erase chemistry
        # that the new table did not contain. Merge before entering the repository's
        # transactional replace operation so existing trace elements remain intact.
        if on_conflict == "update" and name in existing:
            previous_composition, previous_units = _existing_composition_with_units(
                int(existing[name]["id"])
            )
            previous_composition.update(composition)
            previous_units.update(units)
            composition = previous_composition
            units = previous_units

        prepared_rows.append({
            "name": name,
            "metadata": metadata,
            "composition": composition,
            "units": units,
        })

    created, updated, skipped = apply_rock_import_batch(
        project_id,
        prepared_rows,
        on_conflict=on_conflict,
        chemistry_method=chemistry_method,
        source=source,
    )
    return RockImportResult(created, updated, skipped, tuple(warnings))


def delete_rock_with_assets(rock_id: int) -> None:
    """Delete one rock and its stored image files without leaving orphan assets."""
    assets = list_rock_images(int(rock_id))
    paths = [Path(str(asset["stored_path"])) for asset in assets]
    temporary_paths: list[tuple[Path, Path]] = []
    for path in paths:
        if not path.exists():
            continue
        temporary = path.with_suffix(path.suffix + ".deleting")
        path.replace(temporary)
        temporary_paths.append((path, temporary))
    try:
        delete_rock(int(rock_id))
    except Exception:
        for original, temporary in temporary_paths:
            if temporary.exists():
                temporary.replace(original)
        raise
    for _, temporary in temporary_paths:
        temporary.unlink(missing_ok=True)


def composition_dict(rock_id: int) -> dict[str, float]:
    dataframe = get_composition(rock_id)
    return {
        str(row["analyte"]): float(row["value"])
        for _, row in dataframe.iterrows()
        if pd.notna(row.get("value"))
    }


def _finite_value(composition: dict[str, float], key: str) -> float | None:
    try:
        value = float(composition.get(key, np.nan))
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def inferred_whole_rock_fe3_fraction(composition: dict[str, float]) -> float | None:
    """Infer Fe3+/total Fe only where the supplied iron semantics make it possible."""
    ferric_oxide = _finite_value(composition, "Fe2O3")
    ferric_moles = ferric_oxide * 2.0 / M_FE2O3 if ferric_oxide is not None else None
    feot = _finite_value(composition, "FeOt")
    if feot is not None and ferric_moles is not None:
        total_moles = feot / M_FEO
        if total_moles > 0 and 0 <= ferric_moles <= total_moles:
            return float(ferric_moles / total_moles)
    feo = _finite_value(composition, "FeO")
    if feo is not None:
        ferrous_moles = feo / M_FEO
        if ferric_moles is None:
            return 0.0
        total_moles = ferrous_moles + ferric_moles
        return float(ferric_moles / total_moles) if total_moles > 0 else None
    return None


def _total_fe_as_feo(composition: dict[str, float]) -> float | None:
    feot = _finite_value(composition, "FeOt")
    if feot is not None:
        return feot
    fe2o3t = _finite_value(composition, "Fe2O3t")
    if fe2o3t is not None:
        return fe2o3t * FE2O3_TO_FEO_EQUIVALENT
    feo = _finite_value(composition, "FeO")
    if feo is None:
        # Fe2O3 alone is measured ferric iron, not total iron and not a ferrous proxy.
        # Without FeO/FeOt/Fe2O3t there is no defensible Fe2 denominator for Mg#.
        return None
    fe2o3 = _finite_value(composition, "Fe2O3")
    return feo + (fe2o3 or 0.0) * FE2O3_TO_FEO_EQUIVALENT


def whole_rock_mg_number(composition: dict[str, float], fe3_fraction: float | None = None) -> float:
    mgo = _finite_value(composition, "MgO")
    total_feo = _total_fe_as_feo(composition)
    if mgo is None or total_feo is None:
        return np.nan
    fraction = inferred_whole_rock_fe3_fraction(composition) if fe3_fraction is None else float(fe3_fraction)
    if fraction is None:
        fraction = 0.0
    if not 0.0 <= float(fraction) <= 1.0:
        raise ValueError("Доля Fe3+ должна быть в диапазоне 0–1")
    fe2_moles = (total_feo / M_FEO) * (1.0 - float(fraction))
    mg_moles = mgo / M_MGO
    denominator = mg_moles + fe2_moles
    return float(mg_moles / denominator) if denominator > 0 else np.nan


def rhodes_equilibrium_fo(rock_mg_number: float, kd: float = 0.30) -> float:
    mg_number = float(rock_mg_number)
    if not 0 < mg_number < 1:
        return np.nan
    liquid_fe_mg = (1.0 - mg_number) / mg_number
    olivine_fe_mg = float(kd) * liquid_fe_mg
    return float(100.0 / (1.0 + olivine_fe_mg))


def rhodes_lines(rock_mg_number: float, kd_values: tuple[float, ...] = (0.27, 0.30, 0.33)) -> RhodesResult:
    return RhodesResult(
        rock_mg_number=float(rock_mg_number),
        kd_lines={float(kd): rhodes_equilibrium_fo(rock_mg_number, float(kd)) for kd in kd_values},
    )


def measured_olivine_kd(fo_percent: pd.Series, rock_mg_number: float) -> pd.Series:
    mg_number = float(rock_mg_number)
    if not 0 < mg_number < 1:
        raise ValueError("Для Kd whole-rock/melt Mg# должен быть между 0 и 1")
    fo = pd.to_numeric(fo_percent, errors="coerce") / 100.0
    liquid_fe_mg = (1.0 - mg_number) / mg_number
    olivine_fe_mg = (1.0 - fo) / fo
    result = olivine_fe_mg / liquid_fe_mg
    return result.replace([np.inf, -np.inf], np.nan)


def rock_summary(project_id: int | None = None) -> pd.DataFrame:
    records = []
    for rock in list_rocks(project_id):
        comp = composition_dict(int(rock["id"]))
        records.append({
            **rock,
            "Mg#_rock": whole_rock_mg_number(comp),
            "linked_datasets": len(list_mineral_links(int(rock["id"]))),
            "n_chemistry": len(comp),
        })
    return pd.DataFrame(records)
