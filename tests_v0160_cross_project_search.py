from __future__ import annotations

import pandas as pd

from petrolab.search_service import SearchCatalog, literal_search, query_catalog


def _catalog() -> SearchCatalog:
    dataframe = pd.DataFrame([
        {
            "_analysis_id": "a-1",
            "_dataset_id": 10,
            "Проект": "Literature DB",
            "Sample": "AP-1",
            "Минерал": "Apatite",
            "Набор": "Smith apatite",
        },
        {
            "_analysis_id": "a-2",
            "_dataset_id": 10,
            "Проект": "Literature DB",
            "Sample": "AP-1",
            "Минерал": "Apatite",
            "Набор": "Smith apatite",
        },
        {
            "_analysis_id": "p-1",
            "_dataset_id": 20,
            "Проект": "Kola Project",
            "Sample": "19 ТР-1",
            "Минерал": "Phlogopite",
            "Набор": "My mica",
        },
    ])
    return SearchCatalog(
        scope="library",
        dataframe=dataframe,
        datasets=(
            {
                "id": 10,
                "project_id": 1,
                "project_name": "Literature DB",
                "name": "Smith apatite",
                "mineral_key": "apatite",
                "source_filename": "smith2020.xlsx",
                "source_sheet": "apatite",
                "source_kind": "article",
                "row_count": 2,
            },
            {
                "id": 20,
                "project_id": 2,
                "project_name": "Kola Project",
                "name": "My mica",
                "mineral_key": "phlogopite",
                "source_filename": "mica.xlsx",
                "source_sheet": "Sheet1",
                "source_kind": "upload",
                "row_count": 1,
            },
        ),
        samples=(
            {
                "id": 101,
                "project_id": 1,
                "project_name": "Literature DB",
                "name": "AP-1",
                "locality": "Kola Peninsula",
                "field_lithology": "carbonatite",
                "description": "apatite-bearing carbonatite",
                "notes": "",
                "aliases": [],
            },
        ),
        entities=(),
        slide_images=(),
        images=(),
        accessible_dataset_ids=frozenset({20}),
    )


def test_literal_search_is_literal_and_cross_project() -> None:
    catalog = _catalog()
    result = literal_search(catalog.dataframe, "Literature DB")
    assert result["_analysis_id"].tolist() == ["a-1", "a-2"]


def test_query_catalog_keeps_stable_project_and_dataset_identity() -> None:
    results = query_catalog(_catalog(), "apatite")
    assert results.analyses["_analysis_id"].tolist() == ["a-1", "a-2"]
    assert len(results.datasets) == 1
    hit = results.datasets[0]
    assert hit.dataset_id == 10
    assert hit.project_id == 1
    assert hit.project_name == "Literature DB"
    assert hit.analysis_ids == ("a-1", "a-2")


def test_catalog_exposes_current_project_membership_separately_from_provenance() -> None:
    catalog = _catalog()
    results = query_catalog(catalog, "mica")
    assert results.datasets[0].project_name == "Kola Project"
    assert 20 in catalog.accessible_dataset_ids
    assert 10 not in catalog.accessible_dataset_ids


if __name__ == "__main__":
    test_literal_search_is_literal_and_cross_project()
    test_query_catalog_keeps_stable_project_and_dataset_identity()
    test_catalog_exposes_current_project_membership_separately_from_provenance()
    print("v0.16 cross-project search contract: OK")
