from __future__ import annotations

import gc
import io
import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


def _expect_value_error(callable_obj, text: str) -> None:
    try:
        callable_obj()
    except ValueError as exc:
        assert text in str(exc), str(exc)
    else:
        raise AssertionError(f"Expected ValueError containing: {text}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_rock_hardening_", ignore_cleanup_errors=True) as tmp:
        root = Path(tmp)
        os.environ["PETROLAB_DATA_DIR"] = str(root / "data")

        from petrolab.db import (
            add_dataset,
            create_project,
            get_or_create_library_project,
            link_dataset_to_project,
            unlink_dataset_from_project,
        )
        from petrolab.repositories.rock_repository import (
            create_rock,
            get_composition,
            get_rock,
            replace_isotopes,
            set_mineral_links,
            update_rock,
        )
        from petrolab.rock_workspace_export import rock_sample_card_json_bytes, rock_sample_card_xlsx_bytes
        from petrolab.rock_workspace_model import rock_workspace_snapshot
        from petrolab.services.rock_service import import_rocks_wide
        from petrolab.storage import ensure_storage
        from petrolab.ui.pages.whole_rock_compare import _apply_plot_groups

        ensure_storage()
        project_id = create_project("Rock hardening", "")
        library_id = get_or_create_library_project()

        csv_path = root / "library_mica.csv"
        csv_path.write_text("Sample,Point,SiO2\nR1,P1,39.0\n", encoding="utf-8")
        dataset_id = add_dataset(
            library_id,
            "R1 mica from library",
            "phlogopite",
            "mica.xlsx",
            "Sheet1",
            "library-sha",
            str(csv_path),
            1,
            source_kind="managed_copy",
        )
        link_dataset_to_project(project_id, dataset_id, note="working context")

        rock_id = create_rock(project_id, "R1", lithology="lamprophyre")
        set_mineral_links(rock_id, [dataset_id])
        snapshot = rock_workspace_snapshot(project_id, rock_id)
        assert [int(item["id"]) for item in snapshot.linked_datasets] == [dataset_id]
        assert not any("больше не подключены" in warning for warning in snapshot.warnings)

        unlink_dataset_from_project(project_id, dataset_id)
        orphaned = rock_workspace_snapshot(project_id, rock_id)
        assert orphaned.linked_datasets == ()
        assert any(str(dataset_id) in warning and "больше не подключены" in warning for warning in orphaned.warnings)
        _expect_value_error(
            lambda: set_mineral_links(rock_id, [dataset_id]),
            "не подключён к текущему проекту",
        )

        # Partial update must replace provenance only for analytes actually updated.
        import_rocks_wide(
            pd.DataFrame({"Rock": ["R1"], "SiO2": [45.0], "MgO": [12.0]}),
            project_id=project_id,
            name_column="Rock",
            chemistry_method="XRF",
            source="major.xlsx",
            on_conflict="update",
        )
        import_rocks_wide(
            pd.DataFrame({"Rock": ["R1"], "La ppm": [100.0], "Ce ppm": [200.0]}),
            project_id=project_id,
            name_column="Rock",
            chemistry_method="LA-ICP-MS",
            source="trace.xlsx",
            on_conflict="update",
        )
        composition = get_composition(rock_id).set_index("analyte")
        assert float(composition.loc["SiO2", "value"]) == 45.0
        assert composition.loc["SiO2", "method"] == "XRF"
        assert composition.loc["SiO2", "source"] == "major.xlsx"
        assert composition.loc["MgO", "method"] == "XRF"
        assert composition.loc["La [µg/g]", "method"] == "LA-ICP-MS"
        assert composition.loc["La [µg/g]", "source"] == "trace.xlsx"
        assert np.isclose(float(composition.loc["La [µg/g]", "value"]), 100.0)

        _expect_value_error(
            lambda: import_rocks_wide(
                pd.DataFrame({"Rock": ["R1"], "SiO2": [np.inf]}),
                project_id=project_id,
                name_column="Rock",
                chemistry_method="XRF",
                source="bad.xlsx",
                on_conflict="update",
            ),
            "бесконечное/некорректное",
        )
        after_failure = get_composition(rock_id).set_index("analyte")
        assert float(after_failure.loc["SiO2", "value"]) == 45.0
        assert after_failure.loc["SiO2", "source"] == "major.xlsx"

        # All numeric rock metadata/isotope values share one finite-number boundary.
        old_age = get_rock(rock_id)["age_ma"]
        _expect_value_error(lambda: update_rock(rock_id, age_ma=np.inf), "должно быть конечным")
        assert get_rock(rock_id)["age_ma"] == old_age
        _expect_value_error(
            lambda: replace_isotopes(
                rock_id,
                pd.DataFrame([{
                    "system": "Sr", "ratio_name": "87Sr/86Sr", "value": np.inf,
                    "uncertainty": 0.00002, "initial_value": None, "age_ma_used": 380.0,
                    "method": "TIMS", "laboratory": "Lab", "source": "bad", "notes": "",
                }]),
            ),
            "должно быть конечным",
        )
        no_iso = rock_workspace_snapshot(project_id, rock_id)
        assert no_iso.isotope_systems == ()

        # A deliberately incomplete isotope row is visible as incomplete, not as a
        # false positive isotope-system badge.
        replace_isotopes(
            rock_id,
            pd.DataFrame([{
                "system": "Sr", "ratio_name": "87Sr/86Sr", "value": None,
                "uncertainty": None, "initial_value": None, "age_ma_used": None,
                "method": "TIMS", "laboratory": "Lab", "source": "draft", "notes": "",
            }]),
        )
        incomplete_iso = rock_workspace_snapshot(project_id, rock_id)
        assert incomplete_iso.isotope_systems == ()
        assert any("87Sr/86Sr" in warning and "конечного" in warning for warning in incomplete_iso.warnings)

        # Focus is presentation metadata only: it must never overwrite provenance.
        plot_frame = pd.DataFrame({
            "_rock_id": [rock_id, rock_id + 1],
            "Rock": ["R1", "Literature 1"],
            "Источник данных": ["major.xlsx | trace.xlsx", "Smith et al. 2024"],
        })
        grouped = _apply_plot_groups(plot_frame, [rock_id])
        assert grouped["Источник данных"].tolist() == plot_frame["Источник данных"].tolist()
        assert grouped["_rock_plot_group"].tolist() == ["★ R1", "Smith et al. 2024"]

        # Sample-card export is reproducible and keeps per-analyte provenance without
        # leaking the internal project id into the portable rock passport.
        export_snapshot = rock_workspace_snapshot(project_id, rock_id)
        payload = json.loads(rock_sample_card_json_bytes(export_snapshot).decode("utf-8"))
        assert payload["kind"] == "petrolab_rock_sample_card"
        assert payload["schema_version"] == 1
        assert "project_id" not in payload["rock"]
        chemistry_by_analyte = {row["analyte"]: row for row in payload["chemistry"]}
        assert chemistry_by_analyte["SiO2"]["method"] == "XRF"
        assert chemistry_by_analyte["SiO2"]["source"] == "major.xlsx"
        assert chemistry_by_analyte["La [µg/g]"]["method"] == "LA-ICP-MS"
        xlsx = rock_sample_card_xlsx_bytes(export_snapshot)
        workbook = pd.ExcelFile(io.BytesIO(xlsx))
        assert set(workbook.sheet_names) == {
            "Rock", "Chemistry", "Isotopes", "Mineral datasets", "Images", "Data health"
        }
        exported_chemistry = pd.read_excel(io.BytesIO(xlsx), sheet_name="Chemistry")
        exported_si = exported_chemistry.loc[exported_chemistry["analyte"].eq("SiO2")].iloc[0]
        assert exported_si["method"] == "XRF"
        assert exported_si["source"] == "major.xlsx"

        del snapshot, orphaned, composition, after_failure, no_iso, incomplete_iso, grouped, export_snapshot
        del payload, chemistry_by_analyte, xlsx, workbook, exported_chemistry, exported_si
        gc.collect()

    print("rock workspace hardening tests: OK")


if __name__ == "__main__":
    main()
