from __future__ import annotations

import gc
import json
import os
import tempfile
from pathlib import Path

import openpyxl
import pandas as pd


def main() -> None:
    tmp = tempfile.TemporaryDirectory(prefix="petrolab_smoke_")
    try:
        base = Path(tmp.name)
        os.environ["PETROLAB_DATA_DIR"] = str(base / "data")

        from petrolab.db import (
            add_dataset,
            add_image_asset,
            create_project,
            ensure_storage,
            get_dataset,
            list_image_assets,
            list_plot_recipes,
            list_style_profiles,
            load_unified_analyses,
            replace_dataset_rows,
            save_plot_recipe,
            save_style_profile,
            update_analysis_values,
            update_dataset_metadata,
        )
        from petrolab.io_utils import read_tabular_path, sha256_file
        from petrolab.minerals import MINERALS, calculate_formula
        from petrolab.sources import reload_linked_source, source_status, sync_cell_changes

        xlsx = base / "smoke.xlsx"
        source = pd.DataFrame(
            {
                "Sample": ["A1", "A2", "A3"],
                "Group": ["core", "rim", "core"],
                "SiO2": [40.0, 41.0, 42.0],
                "TiO2": [3.0, 4.0, 5.0],
                "MgO": [20.0, 19.0, 18.0],
                "FeO": [8.0, 9.0, 10.0],
            }
        )
        with pd.ExcelWriter(xlsx, engine="openpyxl") as writer:
            source.to_excel(writer, index=False, sheet_name="Mica")

        ensure_storage()
        project_id = create_project("Smoke", "Automated smoke test")
        frame, mapping, source_rows = read_tabular_path(xlsx, "Mica", 1)
        frame = MINERALS["mica"].calculate(frame)
        csv_path = base / "snapshot.csv"
        frame.to_csv(csv_path, index=False)
        dataset_id = add_dataset(
            project_id,
            "Mica set",
            "mica",
            xlsx.name,
            "Mica",
            sha256_file(xlsx),
            str(csv_path),
            len(frame),
            source_path=str(xlsx),
            source_kind="linked",
            header_row=1,
            column_map=mapping,
            sync_enabled=True,
        )
        replace_dataset_rows(dataset_id, frame, source_rows=source_rows)

        unified = load_unified_analyses(project_id, [dataset_id])
        assert len(unified) == 3
        assert "Σ оксидов" in unified.columns
        # Import snapshots retain measured values only. Mg# depends on the Fe
        # assumption, so it must arise in the versioned formula layer instead
        # of being silently baked into raw imported chemistry.
        assert "Mg#" not in unified.columns
        formula = calculate_formula(frame, "mica")
        assert "Mg#_formula" in formula.data.columns
        first = unified.iloc[0]
        analysis_id = str(first["_analysis_id"])

        fake_image = base / "fake.jpg"
        fake_image.write_bytes(b"petrolab-smoke-image")
        add_image_asset(
            project_id,
            dataset_id,
            analysis_id,
            "Конкретная точка анализа",
            "",
            "",
            "BSE",
            "smoke",
            fake_image.name,
            str(fake_image),
        )
        assert len(list_image_assets(analysis_id=analysis_id)) == 1

        change = {
            "analysis_id": analysis_id,
            "dataset_id": dataset_id,
            "source_row": int(first["_source_row"]),
            "column_name": "SiO2",
            "old_value": 40.0,
            "new_value": 44.5,
        }
        backup = sync_cell_changes(get_dataset(dataset_id), [change])
        update_analysis_values([change], synced_to_source=True, source_backup=backup)
        assert Path(backup).exists()

        workbook = openpyxl.load_workbook(xlsx, data_only=True)
        assert workbook["Mica"]["C2"].value == 44.5
        workbook.close()

        workbook = openpyxl.load_workbook(xlsx)
        workbook["Mica"]["D3"] = 7.7
        workbook.save(xlsx)
        workbook.close()
        assert source_status(get_dataset(dataset_id))[0] == "изменён вне ПетроЛаба"

        refreshed, refreshed_map, refreshed_rows, refreshed_hash = reload_linked_source(dataset_id)
        refreshed = MINERALS["mica"].calculate(refreshed)
        replace_dataset_rows(dataset_id, refreshed, source_rows=refreshed_rows, preserve_ids_by_source_row=True)
        update_dataset_metadata(
            dataset_id,
            source_sha256=refreshed_hash,
            column_map_json=refreshed_map,
            row_count=len(refreshed),
        )
        unified2 = load_unified_analyses(project_id, [dataset_id])
        assert str(unified2.iloc[0]["_analysis_id"]) == analysis_id
        assert len(list_image_assets(analysis_id=analysis_id)) == 1

        recipe_id = save_plot_recipe("Si-Ti", {"x": "SiO2", "y": "TiO2", "dataset_ids": [dataset_id]}, project_id)
        assert any(item["id"] == recipe_id for item in list_plot_recipes(project_id))
        style_id = save_style_profile("Group style", "Group", {"core": {"marker": "o"}}, project_id)
        assert any(item["id"] == style_id for item in list_style_profiles(project_id))

        print("core smoke test: OK")
        del source, frame, unified, first, refreshed, unified2, mapping, source_rows, refreshed_map, refreshed_rows
    finally:
        gc.collect()
        tmp.cleanup()


if __name__ == "__main__":
    main()
