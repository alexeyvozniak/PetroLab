from __future__ import annotations

from dataclasses import asdict, dataclass, field

import pandas as pd

from petrolab.analysis_groups import attach_work_groups
from petrolab.db import list_accessible_datasets, list_datasets, list_projects
from petrolab.derived import load_unified_with_derived
from petrolab.generations import attach_generations
from petrolab.measurement_registry import list_entities
from petrolab.repositories.image_repository import list_image_records
from petrolab.sample_registry import list_samples
from petrolab.slides import list_slide_images
from petrolab.source_registry import SOURCE_LABEL_COLUMN, SOURCE_TABLE_COLUMN, attach_study_metadata


SCOPE_PROJECT = "project"
SCOPE_LIBRARY = "library"

_SEARCH_COLUMNS = (
    "Sample", "Образец", "Grain", "Point", "Минерал", "Mineral",
    "Generation", "Генерация", "Method", "Метод", "Набор", "Object", "Объект",
    "Проект", SOURCE_LABEL_COLUMN, SOURCE_TABLE_COLUMN,
)


@dataclass(frozen=True)
class SearchHit:
    kind: str
    title: str
    subtitle: str = ""
    project_id: int | None = None
    project_name: str = ""
    sample_id: int | None = None
    dataset_id: int | None = None
    thin_section_id: int | None = None
    image_id: int | None = None
    analysis_ids: tuple[str, ...] = ()
    payload: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class SearchCatalog:
    scope: str
    dataframe: pd.DataFrame
    datasets: tuple[dict, ...]
    samples: tuple[dict, ...]
    entities: tuple[dict, ...]
    slide_images: tuple[dict, ...]
    images: tuple[dict, ...]
    accessible_dataset_ids: frozenset[int]


@dataclass(frozen=True)
class SearchResults:
    analyses: pd.DataFrame
    samples: tuple[SearchHit, ...]
    datasets: tuple[SearchHit, ...]
    entities: tuple[SearchHit, ...]
    slide_images: tuple[SearchHit, ...]
    images: tuple[SearchHit, ...]

    @property
    def has_any(self) -> bool:
        return not self.analyses.empty or any(
            (self.samples, self.datasets, self.entities, self.slide_images, self.images)
        )


def searchable_columns(dataframe: pd.DataFrame) -> list[str]:
    return [column for column in _SEARCH_COLUMNS if column in dataframe.columns]


def literal_search(dataframe: pd.DataFrame, query: str) -> pd.DataFrame:
    needle = str(query or "").strip()
    if not needle or dataframe.empty:
        return dataframe.iloc[0:0].copy()
    columns = searchable_columns(dataframe)
    if not columns:
        return dataframe.iloc[0:0].copy()
    mask = pd.Series(False, index=dataframe.index, dtype=bool)
    for column in columns:
        mask |= dataframe[column].astype(str).str.contains(needle, case=False, na=False, regex=False)
    return dataframe.loc[mask].copy()


def dict_matches(item: dict, query: str, keys: tuple[str, ...] | None = None) -> bool:
    needle = str(query or "").strip().casefold()
    if not needle:
        return False
    values = [item.get(key) for key in keys] if keys else [
        value for key, value in item.items() if not str(key).startswith("_")
    ]
    return needle in " ".join(str(value or "") for value in values).casefold()


def _science_dataframe(dataset_ids: list[int]) -> pd.DataFrame:
    if not dataset_ids:
        return pd.DataFrame()
    return attach_study_metadata(
        attach_generations(
            attach_work_groups(load_unified_with_derived(None, dataset_ids))
        )
    )


def _project_name_map() -> dict[int, str]:
    return {
        int(project["id"]): str(project.get("name") or "")
        for project in list_projects(include_system=True)
    }


def _all_entities(project_names: dict[int, str]) -> list[dict]:
    rows: list[dict] = []
    for project_id, project_name in project_names.items():
        for item in list_entities(project_id):
            row = dict(item)
            row["project_name"] = project_name
            rows.append(row)
    return rows


def _all_slide_images(project_names: dict[int, str]) -> list[dict]:
    rows: list[dict] = []
    for project_id, project_name in project_names.items():
        for item in list_slide_images(project_id):
            row = asdict(item)
            row["project_name"] = project_name
            rows.append(row)
    return rows


def build_search_catalog(active_project_id: int, *, scope: str = SCOPE_PROJECT) -> SearchCatalog:
    if scope not in {SCOPE_PROJECT, SCOPE_LIBRARY}:
        raise ValueError("Неизвестная область поиска")

    accessible = tuple(list_accessible_datasets(int(active_project_id)))
    accessible_ids = frozenset(int(item["id"]) for item in accessible)

    if scope == SCOPE_LIBRARY:
        project_names = _project_name_map()
        datasets = tuple(list_datasets())
        samples = tuple(list_samples(None))
        entities = tuple(_all_entities(project_names))
        slide_images = tuple(_all_slide_images(project_names))
        images = tuple(list_image_records())
    else:
        project_names = _project_name_map()
        project_name = project_names.get(int(active_project_id), "")
        datasets = accessible
        samples = tuple(list_samples(int(active_project_id)))
        entities = tuple(
            {**item, "project_name": project_name}
            for item in list_entities(int(active_project_id))
        )
        slide_images = tuple(
            {**asdict(item), "project_name": project_name}
            for item in list_slide_images(int(active_project_id))
        )
        images = tuple(list_image_records(project_id=int(active_project_id)))

    dataset_ids = [int(item["id"]) for item in datasets]
    dataframe = _science_dataframe(dataset_ids)
    return SearchCatalog(
        scope=scope,
        dataframe=dataframe,
        datasets=datasets,
        samples=samples,
        entities=entities,
        slide_images=slide_images,
        images=images,
        accessible_dataset_ids=accessible_ids,
    )


def _analysis_ids_for_dataset(dataframe: pd.DataFrame, dataset_id: int) -> tuple[str, ...]:
    if dataframe.empty or "_dataset_id" not in dataframe.columns or "_analysis_id" not in dataframe.columns:
        return ()
    rows = dataframe[pd.to_numeric(dataframe["_dataset_id"], errors="coerce").eq(int(dataset_id))]
    return tuple(rows["_analysis_id"].astype(str).drop_duplicates().tolist())


def _analysis_ids_for_sample(dataframe: pd.DataFrame, sample_name: str) -> tuple[str, ...]:
    if dataframe.empty or "Sample" not in dataframe.columns or "_analysis_id" not in dataframe.columns:
        return ()
    rows = dataframe[dataframe["Sample"].astype(str).str.casefold().eq(str(sample_name).casefold())]
    return tuple(rows["_analysis_id"].astype(str).drop_duplicates().tolist())


def query_catalog(catalog: SearchCatalog, query: str) -> SearchResults:
    analyses = literal_search(catalog.dataframe, query)

    sample_rows = [
        item for item in catalog.samples
        if dict_matches(item, query, ("name", "locality", "field_lithology", "description", "notes", "aliases", "project_name"))
    ]
    dataset_rows = [
        item for item in catalog.datasets
        if dict_matches(item, query, ("name", "mineral_key", "source_filename", "source_sheet", "source_kind", "project_name"))
    ]
    entity_rows = [
        item for item in catalog.entities
        if dict_matches(item, query, ("name", "kind", "sample_name", "parent_name", "description", "project_name"))
    ]
    slide_rows = [
        item for item in catalog.slide_images
        if dict_matches(item, query, ("title", "image_type", "original_filename", "project_name"))
    ]
    image_rows = [item for item in catalog.images if dict_matches(item, query)]

    samples = tuple(
        SearchHit(
            kind="sample",
            title=str(item.get("name") or "Sample"),
            subtitle=str(item.get("locality") or item.get("field_lithology") or ""),
            project_id=int(item["project_id"]) if item.get("project_id") is not None else None,
            project_name=str(item.get("project_name") or ""),
            sample_id=int(item["id"]),
            analysis_ids=_analysis_ids_for_sample(catalog.dataframe, str(item.get("name") or "")),
            payload=dict(item),
        )
        for item in sample_rows
    )
    datasets = tuple(
        SearchHit(
            kind="dataset",
            title=str(item.get("name") or "Массив"),
            subtitle=" · ".join(part for part in (
                str(item.get("mineral_key") or ""),
                f"{int(item.get('row_count') or 0)} анализов",
            ) if part),
            project_id=int(item["project_id"]) if item.get("project_id") is not None else None,
            project_name=str(item.get("project_name") or ""),
            dataset_id=int(item["id"]),
            analysis_ids=_analysis_ids_for_dataset(catalog.dataframe, int(item["id"])),
            payload=dict(item),
        )
        for item in dataset_rows
    )
    entities = tuple(
        SearchHit(
            kind=str(item.get("kind") or "entity"),
            title=str(item.get("name") or "Объект"),
            subtitle=str(item.get("sample_name") or item.get("parent_name") or ""),
            project_id=int(item["project_id"]) if item.get("project_id") is not None else None,
            project_name=str(item.get("project_name") or ""),
            sample_id=int(item["sample_id"]) if item.get("sample_id") is not None else None,
            thin_section_id=int(item["id"]) if str(item.get("kind")) == "thin_section" else (
                int(item["parent_id"]) if item.get("parent_id") is not None else None
            ),
            payload=dict(item),
        )
        for item in entity_rows
    )
    slide_images = tuple(
        SearchHit(
            kind="slide_image",
            title=str(item.get("title") or item.get("original_filename") or "Шлиф"),
            subtitle=str(item.get("image_type") or ""),
            project_id=int(item["project_id"]) if item.get("project_id") is not None else None,
            project_name=str(item.get("project_name") or ""),
            thin_section_id=int(item["thin_section_id"]) if item.get("thin_section_id") is not None else None,
            image_id=int(item["id"]),
            payload=dict(item),
        )
        for item in slide_rows
    )
    images = tuple(
        SearchHit(
            kind="image",
            title=str(item.get("title") or item.get("original_filename") or "Изображение"),
            subtitle=str(item.get("kind") or ""),
            project_id=int(item["project_id"]) if item.get("project_id") is not None else None,
            project_name=str(item.get("project_name") or ""),
            dataset_id=int(item["dataset_id"]) if item.get("dataset_id") is not None else None,
            image_id=int(item["id"]),
            analysis_ids=tuple(str(value) for value in item.get("analysis_ids", []) if str(value)),
            payload=dict(item),
        )
        for item in image_rows
    )
    return SearchResults(
        analyses=analyses,
        samples=samples,
        datasets=datasets,
        entities=entities,
        slide_images=slide_images,
        images=images,
    )
