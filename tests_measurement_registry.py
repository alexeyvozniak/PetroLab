from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pandas as pd


def main() -> None:
    # SQLite on Windows can release a just-closed database handle slightly
    # later than the context manager exits.  The test assertions, not cleanup
    # timing, determine the regression result.
    with tempfile.TemporaryDirectory(prefix="petrolab_measurements_", ignore_cleanup_errors=True) as tmp:
        os.environ["PETROLAB_DATA_DIR"] = str(Path(tmp) / "data")

        from petrolab.db import add_dataset, connect, create_project, get_or_create_library_project, link_dataset_to_project, replace_dataset_rows
        from petrolab.measurement_registry import (
            add_observation,
            create_entity,
            ensure_measurement_registry_schema,
            list_observations,
        )
        from petrolab.sample_registry import create_sample
        from petrolab.storage import ensure_storage

        ensure_storage()
        ensure_measurement_registry_schema()
        project_id = create_project("Measurements", "")
        other_project_id = create_project("Other", "")
        sample_id = create_sample(project_id, "PG-15")
        other_sample_id = create_sample(other_project_id, "OTHER-1")

        grain_id = create_entity(project_id, kind="grain", name="Phl-12", sample_id=sample_id)
        probe = create_entity(project_id, kind="probe_point", parent_id=grain_id, name="P-3")
        crater = create_entity(project_id, kind="la_crater", parent_id=grain_id, name="LA-7")
        aliquot = create_entity(project_id, kind="aliquot", parent_id=grain_id, name="TIMS-1")

        # The same analyte may be retained independently by different methods/forms.
        epma = add_observation(
            project_id,
            entity_id=probe,
            analyte="Ti",
            reported_form="TiO2",
            value=1.15,
            unit="wt.%",
            method="EPMA-WDS",
            instrument="JEOL",
        )
        la = add_observation(
            project_id,
            entity_id=crater,
            analyte="Ti",
            value=7200.0,
            unit="µg/g",
            method="LA-ICP-MS",
            uncertainty=120.0,
        )
        tims = add_observation(
            project_id,
            entity_id=aliquot,
            analyte="Ti",
            value=7050.0,
            unit="µg/g",
            method="TIMS",
            uncertainty=35.0,
        )
        titanium = list_observations(project_id, analyte="Ti")
        assert [row.id for row in titanium] == [epma.id, la.id, tims.id]
        assert [row.method for row in titanium] == ["EPMA-WDS", "LA-ICP-MS", "TIMS"]
        assert epma.reported_form == "TiO2"
        assert la.uncertainty == 120.0

        # Raw chemistry belongs to the common base, but a project may attach
        # its own EPMA point to that same stored analysis without copying it.
        global_base = get_or_create_library_project()
        shared_dataset = add_dataset(
            global_base, "shared probe", "mica", "shared.xlsx", "Data", "shared-sha", "", 1,
        )
        replace_dataset_rows(shared_dataset, pd.DataFrame([{"Sample": "PG-15", "TiO2": 1.15}]))
        with connect() as con:
            shared_analysis = str(con.execute(
                "SELECT analysis_id FROM analysis_rows WHERE dataset_id=?", (shared_dataset,)
            ).fetchone()[0])
        link_dataset_to_project(project_id, shared_dataset, "используется в статье")
        linked = add_observation(
            project_id,
            entity_id=probe,
            analysis_id=shared_analysis,
            dataset_id=shared_dataset,
            analyte="Ti",
            reported_form="TiO2",
            value=1.15,
            unit="wt.%",
            method="EPMA-WDS",
        )
        assert linked.analysis_id == shared_analysis

        # Link validation must reject a dataset/analysis from another project.
        with connect() as con:
            con.execute(
                """INSERT INTO datasets(
                    project_id,name,mineral_key,source_filename,source_sheet,source_sha256,
                    csv_path,row_count,imported_at
                ) VALUES (?,?,?,?,?,?,?,?,?)""",
                (other_project_id, "foreign", "generic", "x.xlsx", "S", "sha", "", 1, "2026-08-14"),
            )
            foreign_dataset = int(con.execute("SELECT last_insert_rowid()").fetchone()[0])
            con.execute(
                "INSERT INTO analysis_rows(analysis_id,dataset_id,row_index,source_row,data_json,updated_at) VALUES (?,?,?,?,?,?)",
                ("foreign-analysis", foreign_dataset, 0, 2, "{}", "2026-08-14"),
            )
            con.commit()
        for kwargs in (
            {"dataset_id": foreign_dataset},
            {"analysis_id": "foreign-analysis"},
        ):
            try:
                add_observation(project_id, analyte="Ti", value=1.0, unit="µg/g", method="test", **kwargs)
            except ValueError:
                pass
            else:
                raise AssertionError("cross-project observation reference must be rejected")

        # Parent/sample hierarchy and scientific numeric guards are explicit.
        try:
            create_entity(project_id, kind="grain", name="bad-sample", sample_id=other_sample_id)
        except ValueError:
            pass
        else:
            raise AssertionError("cross-project sample must be rejected")
        try:
            create_entity(project_id, kind="not-a-kind", name="bad")  # type: ignore[arg-type]
        except ValueError:
            pass
        else:
            raise AssertionError("unknown entity kind must be rejected")
        try:
            add_observation(project_id, entity_id=probe, analyte="Ti", value=float("inf"), unit="µg/g", method="test")
        except ValueError:
            pass
        else:
            raise AssertionError("non-finite observation must be rejected")

    print("measurement registry tests: OK")


if __name__ == "__main__":
    main()
