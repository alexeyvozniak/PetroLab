from __future__ import annotations

from petrolab.ui.pages.distribution import _distribution_dataset_map
from petrolab.ui.pages.equilibrium import _equilibrium_dataset_map


def main() -> None:
    datasets = [
        {
            "id": 11,
            "project_id": 1,
            "project_name": "Project",
            "name": "Mica",
            "mineral_key": "phlogopite",
            "source_filename": "a.xlsx",
            "source_sheet": "Data",
            "row_count": 10,
        },
        {
            "id": 12,
            "project_id": 1,
            "project_name": "Project",
            "name": "Mica",
            "mineral_key": "phlogopite",
            "source_filename": "b.xlsx",
            "source_sheet": "Data",
            "row_count": 12,
        },
    ]
    distribution = _distribution_dataset_map(datasets)
    equilibrium = _equilibrium_dataset_map(datasets)
    assert len(distribution) == 2, distribution
    assert len(equilibrium) == 2, equilibrium
    assert {int(row["id"]) for row in distribution.values()} == {11, 12}
    assert {int(row["id"]) for row in equilibrium.values()} == {11, 12}
    assert all("#" in label or "id" in label.casefold() for label in distribution), distribution
    print("duplicate-dataset UI selector regressions: OK")


if __name__ == "__main__":
    main()
