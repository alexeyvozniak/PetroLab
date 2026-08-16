from __future__ import annotations

from petrolab.ui.pages.analytical_sessions import _session_dataset_map
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
            "source_filename": "same.xlsx",
            "source_sheet": "Data",
            "row_count": 10,
            "imported_at": "2026-08-16T10:00:00+00:00",
        },
        {
            "id": 12,
            "project_id": 1,
            "project_name": "Project",
            "name": "Mica",
            "mineral_key": "phlogopite",
            "source_filename": "same.xlsx",
            "source_sheet": "Data",
            "row_count": 10,
            "imported_at": "2026-08-16T10:05:00+00:00",
        },
    ]
    distribution = _distribution_dataset_map(datasets)
    equilibrium = _equilibrium_dataset_map(datasets)
    sessions = _session_dataset_map(datasets)
    for mapping in (distribution, equilibrium, sessions):
        assert len(mapping) == 2, mapping
        assert set(int(row["id"]) for row in mapping.values()) == {11, 12} if mapping is not sessions else set(mapping.values()) == {11, 12}
        labels = [str(label) for label in mapping]
        assert len(set(labels)) == 2, labels
        assert all("ID" not in label and "id" not in label.casefold() for label in labels), labels
        assert all("same.xlsx / Data" in label for label in labels), labels
        assert all("импорт" in label for label in labels), labels
    print("duplicate-dataset human selector regressions: OK")


if __name__ == "__main__":
    main()
