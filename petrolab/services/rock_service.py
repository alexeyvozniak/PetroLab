from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from petrolab.column_schema import describe_header
from petrolab.repositories.rock_repository import (
    create_rock,
    get_composition,
    get_rock,
    list_mineral_links,
    list_rocks,
    replace_composition,
)


MAJOR_OXIDES = {
    "SiO2", "TiO2", "Al2O3", "Cr2O3", "Fe2O3", "Fe2O3t", "FeO", "FeOt",
    "MnO", "MgO", "CaO", "Na2O", "K2O", "P2O5", "NiO", "BaO", "SrO",
}


@dataclass(frozen=True)
class RockImportResult:
    created_ids: tuple[int, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class RhodesResult:
    rock_mg_number: float
    kd_lines: dict[float, float]


def canonicalize_rock_row(row: pd.Series, excluded_columns: set[str] | None = None) -> tuple[dict[str, float], dict[str, str], list[str]]:
    excluded_columns = excluded_columns or set()
    composition: dict[str, float] = {}
    units: dict[str, str] = {}
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
            warnings.append(f"Повторное поле {canonical}: сохранено первое значение.")
            continue
        composition[canonical] = float(numeric) * float(descriptor.to_canonical_factor)
        units[canonical] = descriptor.canonical_unit or descriptor.source_unit
        if descriptor.warning:
            warnings.append(f"{column}: {descriptor.warning}")
    return composition, units, warnings


def import_rocks_wide(
    dataframe: pd.DataFrame,
    *,
    project_id: int,
    name_column: str,
    metadata_columns: dict[str, str] | None = None,
    chemistry_method: str = "",
    laboratory: str = "",
    source: str = "",
) -> RockImportResult:
    if name_column not in dataframe.columns:
        raise ValueError(f"Колонка названия породы «{name_column}» отсутствует.")
    metadata_columns = metadata_columns or {}
    created: list[int] = []
    warnings: list[str] = []
    excluded = {name_column, *metadata_columns.values()}
    for _, row in dataframe.iterrows():
        name = str(row.get(name_column, "")).strip()
        if not name or name.lower() == "nan":
            continue
        metadata = {key: row.get(column, "") for key, column in metadata_columns.items() if column in dataframe.columns}
        metadata["chemistry_method"] = chemistry_method
        metadata["laboratory"] = laboratory
        rock_id = create_rock(project_id, name, **metadata)
        composition, units, row_warnings = canonicalize_rock_row(row, excluded)
        replace_composition(rock_id, composition, units=units, method=chemistry_method, source=source)
        created.append(rock_id)
        warnings.extend(f"{name}: {message}" for message in row_warnings)
    return RockImportResult(tuple(created), tuple(warnings))


def composition_dict(rock_id: int) -> dict[str, float]:
    dataframe = get_composition(rock_id)
    return {
        str(row["analyte"]): float(row["value"])
        for _, row in dataframe.iterrows()
        if pd.notna(row.get("value"))
    }


def whole_rock_mg_number(composition: dict[str, float], fe3_fraction: float = 0.0) -> float:
    mgo = float(composition.get("MgO", np.nan))
    if not np.isfinite(mgo):
        return np.nan
    if np.isfinite(float(composition.get("FeO", np.nan))):
        feo = float(composition["FeO"])
    elif np.isfinite(float(composition.get("FeOt", np.nan))):
        feo = float(composition["FeOt"])
    elif np.isfinite(float(composition.get("Fe2O3t", np.nan))):
        # Convert total Fe as Fe2O3 to FeO-equivalent while conserving Fe atoms.
        feo = float(composition["Fe2O3t"]) * (2.0 * 71.844 / 159.688)
    else:
        return np.nan
    fe2_moles = (feo / 71.844) * max(0.0, 1.0 - float(fe3_fraction))
    mg_moles = mgo / 40.304
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
    fo = pd.to_numeric(fo_percent, errors="coerce") / 100.0
    liquid_fe_mg = (1.0 - float(rock_mg_number)) / float(rock_mg_number)
    olivine_fe_mg = (1.0 - fo) / fo
    return olivine_fe_mg / liquid_fe_mg


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
