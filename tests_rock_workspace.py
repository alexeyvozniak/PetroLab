from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pandas as pd
from PIL import Image


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_rock_workspace_") as tmp:
        root = Path(tmp)
        os.environ["PETROLAB_DATA_DIR"] = str(root / "data")

        from petrolab.db import add_dataset, create_project, replace_dataset_rows
        from petrolab.repositories.rock_repository import (
            create_rock,
            replace_composition,
            replace_isotopes,
            set_mineral_links,
        )
        from petrolab.rock_workspace_model import (
            major_composition_table,
            rock_workspace_snapshot,
            trace_composition_table,
        )
        from petrolab.services.rock_image_service import save_rock_image
        from petrolab.storage import ensure_storage

        ensure_storage()
        project_id = create_project("Rock workspace", "")
        foreign_project_id = create_project("Foreign", "")
        rock_id = create_rock(
            project_id,
            "KIV-2",
            massif="Kandalaksha",
            locality="Kola",
            lithology="monchiquite",
            age_ma=380.0,
            age_uncertainty_ma=5.0,
            age_method="Rb-Sr",
            laboratory="IGEM",
        )
        composition = {
            "SiO2": 44.0,
            "TiO2": 2.0,
            "Al2O3": 12.0,
            "FeOt": 10.0,
            "MnO": 0.2,
            "MgO": 12.0,
            "CaO": 11.0,
            "Na2O": 2.5,
            "K2O": 3.0,
            "P2O5": 0.8,
            "La [µg/g]": 120.0,
            "Ce [µg/g]": 240.0,
        }
        units = {
            **{key: "wt.%" for key in ["SiO2", "TiO2", "Al2O3", "FeOt", "MnO", "MgO", "CaO", "Na2O", "K2O", "P2O5"]},
            "La [µg/g]": "µg/g",
            "Ce [µg/g]": "µg/g",
        }
        replace_composition(
            rock_id,
            composition,
            units=units,
            method="XRF + ICP-MS",
            source="Vozniak et al., own data",
        )
        replace_isotopes(
            rock_id,
            pd.DataFrame([
                {
                    "system": "Sr",
                    "ratio_name": "87Sr/86Sr",
                    "value": 0.7032,
                    "uncertainty": 0.00002,
                    "initial_value": 0.7029,
                    "age_ma_used": 380.0,
                    "method": "TIMS",
                    "laboratory": "IGEM",
                    "source": "own",
                    "notes": "",
                }
            ]),
        )

        dataset_csv = root / "mica.csv"
        mineral_rows = pd.DataFrame({
            "Sample": ["KIV-2", "KIV-2"],
            "Point": ["P1", "P2"],
            "SiO2": [39.0, 39.5],
            "MgO": [20.0, 19.5],
        })
        mineral_rows.to_csv(dataset_csv, index=False)
        dataset_id = add_dataset(
            project_id,
            "KIV-2 phlogopite",
            "phlogopite",
            "mica.xlsx",
            "Sheet1",
            "rock-workspace-sha",
            str(dataset_csv),
            len(mineral_rows),
            source_kind="managed_copy",
        )
        replace_dataset_rows(dataset_id, mineral_rows, source_rows=[2, 3])
        set_mineral_links(rock_id, [dataset_id])

        image = io.BytesIO()
        Image.new("RGB", (16, 12), "white").save(image, format="PNG")
        save_rock_image(rock_id, "kiv2.png", image.getvalue(), title="KIV-2 hand specimen")

        snapshot = rock_workspace_snapshot(project_id, rock_id)
        assert snapshot.rock["name"] == "KIV-2"
        assert snapshot.major_present == snapshot.major_expected == 10
        assert snapshot.major_fraction == 1.0
        assert snapshot.trace_count == 2
        assert snapshot.isotope_systems == ("Sr",)
        assert snapshot.chemistry_methods == ("XRF + ICP-MS",)
        assert snapshot.chemistry_sources == ("Vozniak et al., own data",)
        assert len(snapshot.linked_datasets) == 1
        assert int(snapshot.linked_datasets[0]["id"]) == dataset_id
        assert len(snapshot.images) == 1
        assert not any("Основные компоненты заполнены не полностью" in value for value in snapshot.warnings)
        assert not any("trace-element" in value for value in snapshot.warnings)

        majors = major_composition_table(snapshot)
        traces = trace_composition_table(snapshot)
        assert set(majors["analyte"]).issuperset({"SiO2", "FeOt", "MgO", "K2O"})
        assert set(traces["analyte"]) == {"La [µg/g]", "Ce [µg/g]"}
        assert set(traces["unit"]) == {"µg/g"}

        incomplete_id = create_rock(project_id, "Incomplete", lithology="basalt")
        replace_composition(
            incomplete_id,
            {"SiO2": 50.0, "MgO": 8.0},
            units={"SiO2": "wt.%", "MgO": "wt.%"},
        )
        incomplete = rock_workspace_snapshot(project_id, incomplete_id)
        assert incomplete.major_present == 2
        assert incomplete.trace_count == 0
        assert any("Основные компоненты заполнены не полностью" in value for value in incomplete.warnings)
        assert any("trace-element" in value for value in incomplete.warnings)
        assert any("источник/provenance" in value for value in incomplete.warnings)

        try:
            rock_workspace_snapshot(foreign_project_id, rock_id)
        except ValueError as exc:
            assert "не относится" in str(exc)
        else:
            raise AssertionError("A rock workspace must reject a rock from another project")

    print("rock workspace tests: OK")


if __name__ == "__main__":
    main()
