from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from petrolab.column_schema import describe_header
from petrolab.db import list_datasets
from petrolab.repositories.rock_repository import (
    get_composition,
    get_isotopes,
    get_rock,
    list_mineral_links,
)
from petrolab.services.rock_image_service import list_rock_images


_MAJOR_COMPONENTS = (
    "SiO2", "TiO2", "Al2O3", "MnO", "MgO", "CaO", "Na2O", "K2O", "P2O5",
)
_IRON_COMPONENTS = ("FeOt", "FeO", "Fe2O3", "Fe2O3t")


@dataclass(frozen=True)
class RockWorkspaceSnapshot:
    rock: dict
    composition: pd.DataFrame
    isotopes: pd.DataFrame
    linked_datasets: tuple[dict, ...]
    images: tuple[dict, ...]
    major_present: int
    major_expected: int
    trace_count: int
    isotope_systems: tuple[str, ...]
    chemistry_methods: tuple[str, ...]
    chemistry_sources: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def major_fraction(self) -> float:
        return float(self.major_present) / float(self.major_expected) if self.major_expected else 0.0



def _clean_values(series: pd.Series) -> tuple[str, ...]:
    values = []
    for value in series.tolist() if not series.empty else []:
        text = str(value or "").strip()
        if text and text.lower() != "nan":
            values.append(text)
    return tuple(dict.fromkeys(values))


def _composition_roles(composition: pd.DataFrame) -> tuple[set[str], int]:
    if composition.empty or "analyte" not in composition.columns:
        return set(), 0
    canonical: set[str] = set()
    trace_count = 0
    for analyte in composition["analyte"].astype(str):
        descriptor = describe_header(analyte)
        name = str(descriptor.canonical_name or analyte)
        canonical.add(name)
        if descriptor.quantity_kind in {"trace_element", "element_concentration"}:
            trace_count += 1
    return canonical, trace_count


def _major_completeness(canonical: set[str]) -> tuple[int, int]:
    present = sum(1 for component in _MAJOR_COMPONENTS if component in canonical)
    iron_present = any(component in canonical for component in _IRON_COMPONENTS)
    present += int(iron_present)
    return present, len(_MAJOR_COMPONENTS) + 1


def rock_workspace_snapshot(project_id: int, rock_id: int) -> RockWorkspaceSnapshot:
    project_id = int(project_id)
    rock_id = int(rock_id)
    rock = get_rock(rock_id)
    if rock is None:
        raise ValueError("Порода больше не существует")
    if int(rock["project_id"]) != project_id:
        raise ValueError("Порода не относится к текущему проекту")

    composition = get_composition(rock_id)
    isotopes = get_isotopes(rock_id)
    linked_ids = set(list_mineral_links(rock_id))
    datasets = [
        dataset for dataset in list_datasets(project_id)
        if int(dataset["id"]) in linked_ids
    ]
    images = list_rock_images(rock_id)

    canonical, trace_count = _composition_roles(composition)
    major_present, major_expected = _major_completeness(canonical)
    isotope_systems = ()
    if not isotopes.empty and "system" in isotopes.columns:
        isotope_systems = _clean_values(isotopes["system"])
    methods = _clean_values(composition.get("method", pd.Series(dtype=object)))
    sources = _clean_values(composition.get("source", pd.Series(dtype=object)))

    warnings: list[str] = []
    if composition.empty:
        warnings.append("Нет валового химического состава")
    elif major_present < major_expected:
        warnings.append(f"Основные компоненты заполнены не полностью: {major_present}/{major_expected}")
    if trace_count == 0:
        warnings.append("Нет распознанных trace-element концентраций")
    if not isotope_systems:
        warnings.append("Изотопные определения не добавлены")
    if not datasets:
        warnings.append("Минералогические datasets пока не связаны с этой породой")
    if not images:
        warnings.append("Нет общей фотографии породы")
    if composition.empty or not sources:
        warnings.append("Для валового состава не указан источник/provenance")

    return RockWorkspaceSnapshot(
        rock=rock,
        composition=composition,
        isotopes=isotopes,
        linked_datasets=tuple(datasets),
        images=tuple(images),
        major_present=major_present,
        major_expected=major_expected,
        trace_count=int(trace_count),
        isotope_systems=tuple(isotope_systems),
        chemistry_methods=tuple(methods),
        chemistry_sources=tuple(sources),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def major_composition_table(snapshot: RockWorkspaceSnapshot) -> pd.DataFrame:
    if snapshot.composition.empty:
        return snapshot.composition.copy()
    rows = []
    for _, row in snapshot.composition.iterrows():
        descriptor = describe_header(row["analyte"])
        if descriptor.quantity_kind == "oxide" or str(descriptor.canonical_name) in _IRON_COMPONENTS:
            rows.append(dict(row))
    return pd.DataFrame(rows)


def trace_composition_table(snapshot: RockWorkspaceSnapshot) -> pd.DataFrame:
    if snapshot.composition.empty:
        return snapshot.composition.copy()
    rows = []
    for _, row in snapshot.composition.iterrows():
        descriptor = describe_header(row["analyte"])
        if descriptor.quantity_kind in {"trace_element", "element_concentration"}:
            rows.append(dict(row))
    return pd.DataFrame(rows)
